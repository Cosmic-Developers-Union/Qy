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
//
// 整数精度：Python `IntValue` 是任意精度 int，所以这里全部用 BigInt 运算，
// 定宽整型的范围也用 BigInt 表示。绝不能把整型载荷退回 `number`。

import { QyTypeError } from '../errors.ts';
import {
  Float16Value,
  Float32Value,
  Float128Value,
  FloatLikeValue,
  FloatValue,
  Int8Value,
  Int16Value,
  Int32Value,
  Int64Value,
  IntegerValue,
  IntValue,
  Chain,
  NumberValue,
  QY_NIL,
  QY_T,
  StringValue,
  Symbol,
  UInt8Value,
  UInt16Value,
  UInt32Value,
  UInt64Value,
  floatPayload,
  integerPayload,
  numberPayloadEquals,
  type QyValue,
} from '../values.ts';
import { performEffect } from './support.ts';

/** 定宽/任意精度整型的构造签名。 */
type IntegerCtor = new (value: bigint) => IntegerValue;
/** 浮点家族的构造签名。 */
type FloatCtor = new (value: number) => FloatLikeValue;
type NumberCtor = IntegerCtor | FloatCtor;

/** 定宽整型的取值范围（BigInt）；IntValue（任意精度）不在表中，不做范围检查。 */
const INTEGER_BOUNDS: Map<IntegerCtor, [bigint, bigint]> = new Map([
  [Int8Value, [-(2n ** 7n), 2n ** 7n - 1n]],
  [Int16Value, [-(2n ** 15n), 2n ** 15n - 1n]],
  [Int32Value, [-(2n ** 31n), 2n ** 31n - 1n]],
  [Int64Value, [-(2n ** 63n), 2n ** 63n - 1n]],
  [UInt8Value, [0n, 2n ** 8n - 1n]],
  [UInt16Value, [0n, 2n ** 16n - 1n]],
  [UInt32Value, [0n, 2n ** 32n - 1n]],
  [UInt64Value, [0n, 2n ** 64n - 1n]],
]);

const INTEGER_CTORS: IntegerCtor[] = [
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
const FLOAT_CTORS: FloatCtor[] = [FloatValue, Float16Value, Float32Value, Float128Value];

/** 把宿主 int/bigint/float 升格为 Qy 语义数值（`_coerce_host_number`）。 */
export function coerceHostNumber(value: QyValue): QyValue {
  if (value instanceof NumberValue) return value;
  if (typeof value === 'boolean') return value;
  if (typeof value === 'bigint') return new IntValue(value);
  if (typeof value === 'number') {
    if (Number.isInteger(value)) return new IntValue(value);
    return new FloatValue(value);
  }
  return value;
}

function typeName(value: QyValue): string {
  // 与 Python `qy.sem.classify.value_type` 一致：返回 Qy 类型标签，而不是宿主类名。
  if (value instanceof NumberValue) return value.typeName;
  if (value instanceof Symbol) return 'symbol';
  if (value instanceof Chain) return 'chain';
  const named = (value as { typeName?: string }).typeName;
  if (named !== undefined) return named;
  if (value === null || value === undefined) return 'none';
  if (typeof value === 'boolean') return 'bool';
  if (typeof value === 'bigint' || typeof value === 'number') return 'number';
  if (typeof value === 'string') return 'string';
  return 'any';
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

/** 定宽整型越界检查（`_check_integer_range`）；IntValue 不检查。 */
export function checkIntegerRange(value: bigint, type: IntegerCtor, op: string): bigint {
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

export function checkFloatFinite(value: number, name: string, op: string): number {
  if (Number.isNaN(value) || !Number.isFinite(value)) {
    performEffect('numeric-overflow', { type: name, operation: op, result: value });
  }
  return value;
}

function makeInteger(type: IntegerCtor, value: bigint): IntegerValue {
  return new type(value);
}

function makeFloat(type: FloatCtor, value: number): FloatLikeValue {
  return new type(value);
}

type IntegerKernel = (type: IntegerCtor, args: NumberValue[]) => NumberValue;
type FloatKernel = (type: FloatCtor, args: NumberValue[]) => NumberValue;

function dispatchOp(
  op: string,
  args: QyValue[],
  integerKernel: IntegerKernel,
  floatKernel: FloatKernel,
): NumberValue {
  const coerced = args.map(coerceHostNumber);
  const valueType = ensureSameNumberType(coerced, op);
  const typed = coerced.filter((item): item is NumberValue => item instanceof NumberValue);
  if (INTEGER_CTORS.some((ctor) => ctor === valueType)) {
    return integerKernel(valueType as IntegerCtor, typed);
  }
  if (FLOAT_CTORS.some((ctor) => ctor === valueType)) {
    return floatKernel(valueType as FloatCtor, typed);
  }
  throw new QyTypeError(`${op} has no kernel for number type ${typeName(typed[0])}`);
}

// -- 整数内核（全部 BigInt） -------------------------------------------------

function integerAdd(type: IntegerCtor, args: NumberValue[]): NumberValue {
  let total = 0n;
  for (const arg of args) total += integerPayload(arg);
  return makeInteger(type, checkIntegerRange(total, type, '+'));
}

function integerSub(type: IntegerCtor, args: NumberValue[]): NumberValue {
  if (args.length === 1) return makeInteger(type, checkIntegerRange(-integerPayload(args[0]), type, '-'));
  let result = integerPayload(args[0]);
  for (const arg of args.slice(1)) result -= integerPayload(arg);
  return makeInteger(type, checkIntegerRange(result, type, '-'));
}

function integerMul(type: IntegerCtor, args: NumberValue[]): NumberValue {
  let result = 1n;
  for (const arg of args) result *= integerPayload(arg);
  return makeInteger(type, checkIntegerRange(result, type, '*'));
}

/** Python `//`（向负无穷取整）。BigInt `/` 是向零截断，所以这里显式修正。 */
export function floorDiv(a: bigint, b: bigint): bigint {
  const quotient = a / b;
  const remainder = a % b;
  return remainder !== 0n && remainder < 0n !== b < 0n ? quotient - 1n : quotient;
}

/**
 * Python 二元整数除法里 `int(result / divisor)` 的对应实现。
 *
 * `qy/session/number_ops.py::_integer_div` 在"异号且余数非零"时走的是
 * **float 真除法**再截断，所以超大整数会因此丢精度（Python 侧宿主缺陷）。
 * 为了与 Python 逐字节一致，这里同样走 double：JS `Number(bigint)` 与
 * CPython 的 int→double 都是正确舍入，`Math.trunc` 与 `int()` 都是向零截断。
 * 结果超出 double 范围时 Python 抛 OverflowError，这里让 `BigInt()` 抛
 * RangeError，同样会被 `call` 包装成运行时错误。
 */
function truncDivViaFloat(a: bigint, b: bigint): bigint {
  return BigInt(Math.trunc(Number(a) / Number(b)));
}

function integerDiv(type: IntegerCtor, args: NumberValue[]): NumberValue {
  if (args.length === 1) {
    const first = integerPayload(args[0]);
    if (first === 0n) performEffect('divide-by-zero', { operator: '/' }, true);
    // 注意：Python `_integer_div` 的单参数分支是 `1 // first`（floor），
    // 与二元分支的向零截断不同。见 qy/session/number_ops.py:244-249。
    return makeInteger(type, checkIntegerRange(floorDiv(1n, first), type, '/'));
  }
  let result = integerPayload(args[0]);
  for (const arg of args.slice(1)) {
    const divisor = integerPayload(arg);
    if (divisor === 0n) performEffect('divide-by-zero', { operator: '/' }, true);
    // 逐字复刻 Python：异号且余数非零 → `int(result / divisor)`（float），
    // 否则 `result // divisor`（floor；此处与 BigInt 向零截断等价）。
    const signsDiffer = result < 0n !== divisor < 0n;
    result = signsDiffer && result % divisor !== 0n ? truncDivViaFloat(result, divisor) : result / divisor;
  }
  return makeInteger(type, checkIntegerRange(result, type, '/'));
}

/** Python 的 `%`（结果符号跟随除数）。BigInt `%` 符号跟随被除数，需要修正。 */
export function pyMod(a: bigint, b: bigint): bigint {
  const result = a % b;
  return result !== 0n && result < 0n !== b < 0n ? result + b : result;
}

function integerMod(type: IntegerCtor, args: NumberValue[]): NumberValue {
  if (args.length !== 2) throw new QyTypeError('mod expects exactly 2 arguments');
  const a = integerPayload(args[0]);
  const b = integerPayload(args[1]);
  if (b === 0n) performEffect('divide-by-zero', { operator: 'mod' }, false);
  return makeInteger(type, checkIntegerRange(pyMod(a, b), type, 'mod'));
}

// -- 浮点内核 ---------------------------------------------------------------

function floatNameOf(type: FloatCtor): string {
  return (type as unknown as { typeName?: string }).typeName ?? type.name;
}

function floatAdd(type: FloatCtor, args: NumberValue[]): NumberValue {
  let total = 0;
  for (const arg of args) total += floatPayload(arg);
  return makeFloat(type, checkFloatFinite(total, floatNameOf(type), '+'));
}

function floatSub(type: FloatCtor, args: NumberValue[]): NumberValue {
  if (args.length === 1) return makeFloat(type, -floatPayload(args[0]));
  let result = floatPayload(args[0]);
  for (const arg of args.slice(1)) result -= floatPayload(arg);
  return makeFloat(type, checkFloatFinite(result, floatNameOf(type), '-'));
}

function floatMul(type: FloatCtor, args: NumberValue[]): NumberValue {
  let result = 1;
  for (const arg of args) result *= floatPayload(arg);
  return makeFloat(type, checkFloatFinite(result, floatNameOf(type), '*'));
}

function floatDiv(type: FloatCtor, args: NumberValue[]): NumberValue {
  if (args.length === 1) {
    const first = floatPayload(args[0]);
    if (first === 0) performEffect('divide-by-zero', { operator: '/' }, true);
    return makeFloat(type, checkFloatFinite(1 / first, floatNameOf(type), '/'));
  }
  let result = floatPayload(args[0]);
  for (const arg of args.slice(1)) {
    const divisor = floatPayload(arg);
    if (divisor === 0) performEffect('divide-by-zero', { operator: '/' }, true);
    result /= divisor;
  }
  return makeFloat(type, checkFloatFinite(result, floatNameOf(type), '/'));
}

function floatMod(type: FloatCtor, args: NumberValue[]): NumberValue {
  if (args.length !== 2) throw new QyTypeError('mod expects exactly 2 arguments');
  const a = floatPayload(args[0]);
  const b = floatPayload(args[1]);
  if (b === 0) performEffect('divide-by-zero', { operator: 'mod' }, false);
  // 与 integerMod / Python `%` 一致：结果符号跟随除数（floored）；JS `%` 是截断余数。
  const remainder = a % b;
  const result = remainder !== 0 && remainder < 0 !== b < 0 ? remainder + b : remainder;
  return makeFloat(type, checkFloatFinite(result, floatNameOf(type), 'mod'));
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

function integerRemainder(type: IntegerCtor, args: NumberValue[]): NumberValue {
  if (args.length !== 2) throw new QyTypeError('remainder expects exactly 2 arguments');
  const a = integerPayload(args[0]);
  const b = integerPayload(args[1]);
  if (b === 0n) performEffect('divide-by-zero', { operator: 'remainder' }, false);
  // BigInt `%` 是截断余数：结果符号跟随被除数（与 mod 的 floored 相对）。
  return makeInteger(type, checkIntegerRange(a % b, type, 'remainder'));
}

function floatRemainder(type: FloatCtor, args: NumberValue[]): NumberValue {
  if (args.length !== 2) throw new QyTypeError('remainder expects exactly 2 arguments');
  const a = floatPayload(args[0]);
  const b = floatPayload(args[1]);
  if (b === 0) performEffect('divide-by-zero', { operator: 'remainder' }, false);
  return makeFloat(type, checkFloatFinite(a % b, floatNameOf(type), 'remainder'));
}

export function remainder(...args: QyValue[]): NumberValue {
  return dispatchOp('remainder', args, integerRemainder, floatRemainder);
}

/** 对应 `number_ops._number_p`：值是否为 number（Qy 语义或宿主数字）。 */
export function numberP(value: QyValue): QyValue {
  if (value instanceof NumberValue) return QY_T;
  if (typeof value === 'boolean') return QY_NIL;
  return typeof value === 'number' ? QY_T : QY_NIL;
}

const INT_TEXT = /^[+-]?\d(?:_?\d)*$/;
const FLOAT_TEXT = /^[+-]?(?:\d(?:_?\d)*\.(?:\d(?:_?\d)*)?|\.\d(?:_?\d)*|\d(?:_?\d)*)(?:[eE][+-]?\d+)?$/;

/** 对应 `number_ops._string_to_number`：字符串/符号拼写 → number，失败返回 nil。 */
export function stringToNumber(value: QyValue): QyValue {
  let text: string;
  if (value instanceof StringValue) text = value.value;
  else if (value instanceof Symbol) text = value.name;
  else if (typeof value === 'string') text = value;
  else return QY_NIL;
  const trimmed = text.trim();
  if (INT_TEXT.test(trimmed)) {
    return new IntValue(BigInt(trimmed.replace(/_/g, '')));
  }
  if (FLOAT_TEXT.test(trimmed)) {
    const parsed = Number(trimmed.replace(/_/g, ''));
    if (Number.isFinite(parsed)) return new FloatValue(parsed);
  }
  return QY_NIL;
}

/** 同 concrete 类型数值的三路比较（-1 / 0 / 1）。 */
function compareNumberValues(left: NumberValue, right: NumberValue): number {
  if (left.isInteger && right.isInteger) {
    const a = integerPayload(left);
    const b = integerPayload(right);
    return a < b ? -1 : a > b ? 1 : 0;
  }
  const a = floatPayload(left);
  const b = floatPayload(right);
  return a < b ? -1 : a > b ? 1 : 0;
}

function ordering(op: string, args: QyValue[], accept: (comparison: number) => boolean): QyValue {
  if (args.length !== 2) throw new QyTypeError(`${op} expects exactly 2 arguments`);
  const coerced = args.map(coerceHostNumber);
  ensureSameNumberType(coerced, op);
  const [left, right] = coerced;
  if (!(left instanceof NumberValue) || !(right instanceof NumberValue)) {
    throw new QyTypeError(`${op} expects numbers`);
  }
  return accept(compareNumberValues(left, right)) ? QY_T : QY_NIL;
}

export function lt(...args: QyValue[]): QyValue {
  return ordering('<', args, (comparison) => comparison < 0);
}
export function gt(...args: QyValue[]): QyValue {
  return ordering('>', args, (comparison) => comparison > 0);
}
export function le(...args: QyValue[]): QyValue {
  return ordering('<=', args, (comparison) => comparison <= 0);
}
export function ge(...args: QyValue[]): QyValue {
  return ordering('>=', args, (comparison) => comparison >= 0);
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
    return numberPayloadEquals(a.value, b.value) ? QY_T : QY_NIL;
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
  if (left instanceof NumberValue && right instanceof NumberValue) {
    return numberPayloadEquals(left.value, right.value);
  }
  if (left instanceof StringValue && right instanceof StringValue) return left.value === right.value;
  if (left instanceof Symbol && right instanceof Symbol) return left.name === right.name;
  if (Array.isArray(left) && Array.isArray(right)) {
    return left.length === right.length && left.every((item, index) => pyEquals(item, right[index]));
  }
  return false;
}
