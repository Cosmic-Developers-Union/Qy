// number-ss 的算术/比较算子。
//
// 真源：`qy/session/number_ops.py`。核心约束（必须有，否则语料语义会变）：
//
//   1. 不做隐式提升：所有参数必须是同一个 concrete `NumberValue` 类型，
//      否则触发 `unsupported-operation` effect（number_ops._ensure_same_number_type）；
//   2. 除零触发 `divide-by-zero`（`/` 可恢复，`mod` 不可恢复）；
//   3. 定宽整型/浮点越界触发 `numeric-overflow`；
//   4. 整数除法向零截断（不是 Python `//` 的向下取整）；
//   5. `=` 是同 concrete 类型的数值相等；两侧非数值时退化为 identity 比较；
//   6. `==` 是宿主 `==` 语义（`_py_eq`）。

import { QyTypeError } from '../errors.ts';
import {
  Float16Value,
  Float32Value,
  Float128Value,
  FloatValue,
  Int8Value,
  Int16Value,
  Int32Value,
  Int64Value,
  IntValue,
  NumberValue,
  QY_NIL,
  QY_T,
  StringValue,
  Symbol,
  UInt8Value,
  UInt16Value,
  UInt32Value,
  UInt64Value,
  type QyValue,
} from '../values.ts';
import { performEffect } from './support.ts';

type NumberCtor = new (value: number) => NumberValue;

/** 定宽整型的取值范围；IntValue（任意精度）不在表中，不做范围检查。 */
const INTEGER_BOUNDS: Map<NumberCtor, [number, number]> = new Map([
  [Int8Value, [-(2 ** 7), 2 ** 7 - 1]],
  [Int16Value, [-(2 ** 15), 2 ** 15 - 1]],
  [Int32Value, [-(2 ** 31), 2 ** 31 - 1]],
  [Int64Value, [-(2 ** 63), 2 ** 63 - 1]],
  [UInt8Value, [0, 2 ** 8 - 1]],
  [UInt16Value, [0, 2 ** 16 - 1]],
  [UInt32Value, [0, 2 ** 32 - 1]],
  [UInt64Value, [0, 2 ** 64 - 1]],
]);

const INTEGER_CTORS: NumberCtor[] = [
  IntValue,
  Int8Value,
  Int16Value,
  Int32Value,
  Int64Value,
  UInt8Value,
  UInt16Value,
  UInt32Value,
  UInt64Value,
];
const FLOAT_CTORS: NumberCtor[] = [FloatValue, Float16Value, Float32Value, Float128Value];

/** 把宿主 int/float 升格为 Qy 语义数值（`_coerce_host_number`）。 */
export function coerceHostNumber(value: QyValue): QyValue {
  if (value instanceof NumberValue) return value;
  if (typeof value === 'boolean') return value;
  if (typeof value === 'number') {
    return Number.isInteger(value) ? new IntValue(value) : new FloatValue(value);
  }
  return value;
}

function typeName(value: QyValue): string {
  if (value instanceof NumberValue) return value.typeName;
  if (value === null || value === undefined) return 'NoneType';
  if (typeof value === 'boolean') return 'bool';
  if (typeof value === 'number') return 'int';
  if (typeof value === 'string') return 'str';
  if (value instanceof Symbol) return 'Symbol';
  if (value instanceof StringValue) return 'StringValue';
  return (value as { typeName?: string }).typeName ?? 'object';
}

/** 要求所有参数是同一个 concrete NumberValue 类型（`_ensure_same_number_type`）。 */
function ensureSameNumberType(args: QyValue[], op: string): NumberCtor {
  if (args.length === 0) throw new QyTypeError(`${op} requires at least one argument`);
  const head = args[0];
  if (!(head instanceof NumberValue)) {
    throw new QyTypeError(`${op} expects a number, got ${typeName(head)}`);
  }
  const headType = head.constructor as NumberCtor;
  for (let index = 1; index < args.length; index += 1) {
    const arg = args[index];
    if ((arg as object | null)?.constructor !== headType) {
      performEffect('unsupported-operation', {
        operator: op,
        left_type: head.typeName,
        right_type: typeName(arg),
        argument_index: index,
      });
    }
  }
  return headType;
}

function checkIntegerRange(value: number, type: NumberCtor, op: string): number {
  const bounds = INTEGER_BOUNDS.get(type);
  if (bounds === undefined) return value;
  const [minimum, maximum] = bounds;
  if (value < minimum || value > maximum) {
    performEffect('numeric-overflow', {
      type: (type as unknown as { typeName?: string }).typeName ?? type.name,
      operation: op,
      result: value,
      min: minimum,
      max: maximum,
    });
  }
  return value;
}

function checkFloatFinite(value: number, name: string, op: string): number {
  if (Number.isNaN(value) || !Number.isFinite(value)) {
    performEffect('numeric-overflow', { type: name, operation: op, result: value });
  }
  return value;
}

function makeNumber(type: NumberCtor, value: number): NumberValue {
  return new type(value);
}

type Kernel = (type: NumberCtor, args: NumberValue[]) => NumberValue;

function dispatchOp(op: string, args: QyValue[], integerKernel: Kernel, floatKernel: Kernel): NumberValue {
  const coerced = args.map(coerceHostNumber);
  const valueType = ensureSameNumberType(coerced, op);
  const typed = coerced.filter((item): item is NumberValue => item instanceof NumberValue);
  if (INTEGER_CTORS.includes(valueType)) return integerKernel(valueType, typed);
  if (FLOAT_CTORS.includes(valueType)) return floatKernel(valueType, typed);
  throw new QyTypeError(`${op} has no kernel for number type ${typeName(typed[0])}`);
}

// -- 整数内核 ---------------------------------------------------------------

function integerAdd(type: NumberCtor, args: NumberValue[]): NumberValue {
  let total = 0;
  for (const arg of args) total += arg.value;
  return makeNumber(type, checkIntegerRange(total, type, '+'));
}

function integerSub(type: NumberCtor, args: NumberValue[]): NumberValue {
  if (args.length === 1) return makeNumber(type, checkIntegerRange(-args[0].value, type, '-'));
  let result = args[0].value;
  for (const arg of args.slice(1)) result -= arg.value;
  return makeNumber(type, checkIntegerRange(result, type, '-'));
}

function integerMul(type: NumberCtor, args: NumberValue[]): NumberValue {
  let result = 1;
  for (const arg of args) result *= arg.value;
  return makeNumber(type, checkIntegerRange(result, type, '*'));
}

/** 向零截断的整数除法（number_ops._integer_div：`int(a / b)`）。 */
function truncDiv(a: number, b: number): number {
  return Math.trunc(a / b);
}

function integerDiv(type: NumberCtor, args: NumberValue[]): NumberValue {
  if (args.length === 1) {
    const first = args[0].value;
    if (first === 0) performEffect('divide-by-zero', { operator: '/' }, true);
    return makeNumber(type, checkIntegerRange(truncDiv(1, first), type, '/'));
  }
  let result = args[0].value;
  for (const arg of args.slice(1)) {
    const divisor = arg.value;
    if (divisor === 0) performEffect('divide-by-zero', { operator: '/' }, true);
    result = truncDiv(result, divisor);
  }
  return makeNumber(type, checkIntegerRange(result, type, '/'));
}

/** Python 的 `%`（结果符号跟随除数）。 */
function pyMod(a: number, b: number): number {
  const result = a % b;
  return result !== 0 && result < 0 !== b < 0 ? result + b : result;
}

function integerMod(type: NumberCtor, args: NumberValue[]): NumberValue {
  if (args.length !== 2) throw new QyTypeError('mod expects exactly 2 arguments');
  const a = args[0].value;
  const b = args[1].value;
  if (b === 0) performEffect('divide-by-zero', { operator: 'mod' }, false);
  return makeNumber(type, checkIntegerRange(pyMod(a, b), type, 'mod'));
}

// -- 浮点内核 ---------------------------------------------------------------

function floatNameOf(type: NumberCtor): string {
  return (type as unknown as { typeName?: string }).typeName ?? type.name;
}

function floatAdd(type: NumberCtor, args: NumberValue[]): NumberValue {
  let total = 0;
  for (const arg of args) total += arg.value;
  return makeNumber(type, checkFloatFinite(total, floatNameOf(type), '+'));
}

function floatSub(type: NumberCtor, args: NumberValue[]): NumberValue {
  if (args.length === 1) return makeNumber(type, -args[0].value);
  let result = args[0].value;
  for (const arg of args.slice(1)) result -= arg.value;
  return makeNumber(type, checkFloatFinite(result, floatNameOf(type), '-'));
}

function floatMul(type: NumberCtor, args: NumberValue[]): NumberValue {
  let result = 1;
  for (const arg of args) result *= arg.value;
  return makeNumber(type, checkFloatFinite(result, floatNameOf(type), '*'));
}

function floatDiv(type: NumberCtor, args: NumberValue[]): NumberValue {
  if (args.length === 1) {
    const first = args[0].value;
    if (first === 0) performEffect('divide-by-zero', { operator: '/' }, true);
    return makeNumber(type, checkFloatFinite(1 / first, floatNameOf(type), '/'));
  }
  let result = args[0].value;
  for (const arg of args.slice(1)) {
    const divisor = arg.value;
    if (divisor === 0) performEffect('divide-by-zero', { operator: '/' }, true);
    result /= divisor;
  }
  return makeNumber(type, checkFloatFinite(result, floatNameOf(type), '/'));
}

function floatMod(type: NumberCtor, args: NumberValue[]): NumberValue {
  if (args.length !== 2) throw new QyTypeError('mod expects exactly 2 arguments');
  const a = args[0].value;
  const b = args[1].value;
  if (b === 0) performEffect('divide-by-zero', { operator: 'mod' }, false);
  return makeNumber(type, checkFloatFinite(a - b * Math.trunc(a / b), floatNameOf(type), 'mod'));
}

// -- 公开算子 ---------------------------------------------------------------

export function add(...args: QyValue[]): NumberValue {
  return dispatchOp('+', args, integerAdd, floatAdd);
}
export function sub(...args: QyValue[]): NumberValue {
  return dispatchOp('-', args, integerSub, floatSub);
}
export function mul(...args: QyValue[]): NumberValue {
  return dispatchOp('*', args, integerMul, floatMul);
}
export function div(...args: QyValue[]): NumberValue {
  return dispatchOp('/', args, integerDiv, floatDiv);
}
export function mod(...args: QyValue[]): NumberValue {
  return dispatchOp('mod', args, integerMod, floatMod);
}

function ordering(op: string, args: QyValue[], compare: (a: number, b: number) => boolean): QyValue {
  if (args.length !== 2) throw new QyTypeError(`${op} expects exactly 2 arguments`);
  const coerced = args.map(coerceHostNumber);
  ensureSameNumberType(coerced, op);
  const [left, right] = coerced;
  if (!(left instanceof NumberValue) || !(right instanceof NumberValue)) {
    throw new QyTypeError(`${op} expects numbers`);
  }
  return compare(left.value, right.value) ? QY_T : QY_NIL;
}

export function lt(...args: QyValue[]): QyValue {
  return ordering('<', args, (a, b) => a < b);
}
export function gt(...args: QyValue[]): QyValue {
  return ordering('>', args, (a, b) => a > b);
}
export function le(...args: QyValue[]): QyValue {
  return ordering('<=', args, (a, b) => a <= b);
}
export function ge(...args: QyValue[]): QyValue {
  return ordering('>=', args, (a, b) => a >= b);
}

/** `=`：同 concrete 数值类型相等；非数值退化为 identity（number_ops._num_eq）。 */
export function numEq(left: QyValue, right: QyValue): QyValue {
  if (typeof left === 'boolean' || typeof right === 'boolean') {
    return left === right ? QY_T : QY_NIL;
  }
  const a = coerceHostNumber(left);
  const b = coerceHostNumber(right);
  if (a instanceof NumberValue && b instanceof NumberValue) {
    if ((a as object).constructor !== (b as object).constructor) {
      performEffect('unsupported-operation', {
        operator: '=',
        left_type: a.typeName,
        right_type: b.typeName,
      });
    }
    return a.value === b.value ? QY_T : QY_NIL;
  }
  return left === right ? QY_T : QY_NIL;
}

/** `==`：宿主 `==` 语义（number_ops._py_eq）。 */
export function pyEq(left: QyValue, right: QyValue): QyValue {
  return pyEquals(left, right) ? QY_T : QY_NIL;
}

/**
 * Python `==` 的近似实现。
 *
 * 覆盖语料需要的几类：数值按值、StringValue 按值、Symbol 按名字（dataclass
 * 结构相等）、nil/T/none 单例、容器按元素。
 */
export function pyEquals(left: QyValue, right: QyValue): boolean {
  if (left === right) return true;
  if (left instanceof NumberValue && right instanceof NumberValue) return left.value === right.value;
  if (left instanceof StringValue && right instanceof StringValue) return left.value === right.value;
  if (left instanceof Symbol && right instanceof Symbol) return left.name === right.name;
  if (Array.isArray(left) && Array.isArray(right)) {
    return left.length === right.length && left.every((item, index) => pyEquals(item, right[index]));
  }
  return false;
}
