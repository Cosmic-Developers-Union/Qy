// qy.int8..qy.float128 具体数值空间（对应 `qy/std/numeric_spaces.py`）。
//
// 每个模块提供：构造器、类型谓词、类型化算术/比较/位运算，以及 min-value /
// max-value / bits 常量值。语义与 Python 的 `_make_integer_space` /
// `_make_float_space` 逐条对齐（整数除法截断、`mod` floored、`rem` 截断，与 `qy.num`
// 的 `/` / `mod` / `remainder` 一致）。

import { QyTypeError } from '../errors.ts';
import { checkFloatFinite, checkIntegerRange, floorDiv, pyMod } from './arithmetic.ts';
import { performEffect } from './support.ts';
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
  IntValue,
  IntegerValue,
  NumberValue,
  QY_NIL,
  QY_T,
  UInt8Value,
  UInt16Value,
  UInt32Value,
  UInt64Value,
  floatPayload,
  integerPayload,
  type QyValue,
} from '../values.ts';

type IntegerCtor = new (value: bigint) => IntegerValue;
type FloatCtor = new (value: number) => FloatLikeValue;
type Binding = (...args: QyValue[]) => QyValue;

export interface NumberSpace {
  name: string;
  operators: Record<string, Binding>;
  values: Record<string, QyValue>;
}

function makeIntegerSpace(
  name: string,
  type: IntegerCtor,
  bits: number,
  min: bigint,
  max: bigint,
): NumberSpace {
  const requireTyped = (value: QyValue, op: string): bigint => {
    if (!(value instanceof IntegerValue) || (value.constructor as unknown) !== type) {
      throw new QyTypeError(`${name}.${op} expects ${name}`);
    }
    return integerPayload(value);
  };
  const check = (value: bigint, op: string): bigint => checkIntegerRange(value, type, op);
  const signed = min < 0n;
  const operators: Record<string, Binding> = {
    [name]: (...args: QyValue[]): QyValue => {
      const value = args[0];
      let raw: bigint;
      if (value instanceof IntegerValue) raw = integerPayload(value);
      else if (typeof value === 'bigint') raw = value;
      else if (typeof value === 'number' && Number.isInteger(value)) raw = BigInt(value);
      else throw new QyTypeError(`${name} constructor expects integer`);
      return new type(check(raw, 'constructor'));
    },
    [`${name}?`]: (value: QyValue): QyValue => (value instanceof type ? QY_T : QY_NIL),
    '+': (...args: QyValue[]): QyValue => {
      let total = 0n;
      for (const arg of args) total += requireTyped(arg, '+');
      return new type(check(total, '+'));
    },
    '-': (...args: QyValue[]): QyValue => {
      if (args.length === 1) return new type(check(-requireTyped(args[0], '-'), '-'));
      let result = requireTyped(args[0], '-');
      for (const arg of args.slice(1)) result -= requireTyped(arg, '-');
      return new type(check(result, '-'));
    },
    '*': (...args: QyValue[]): QyValue => {
      let result = 1n;
      for (const arg of args) result *= requireTyped(arg, '*');
      return new type(check(result, '*'));
    },
    '/': (...args: QyValue[]): QyValue => {
      let result: bigint;
      if (args.length === 1) {
        const first = requireTyped(args[0], '/');
        if (first === 0n) performEffect('divide-by-zero', { operator: '/' }, false);
        result = floorDiv(1n, first);
      } else {
        result = requireTyped(args[0], '/');
        for (const arg of args.slice(1)) {
          const divisor = requireTyped(arg, '/');
          if (divisor === 0n) performEffect('divide-by-zero', { operator: '/' }, false);
          // BigInt `/` 向零截断，与 `qy.num` 的整数 `/` 一致。
          result = result / divisor;
        }
      }
      return new type(check(result, '/'));
    },
    mod: (a: QyValue, b: QyValue): QyValue => {
      const left = requireTyped(a, 'mod');
      const right = requireTyped(b, 'mod');
      if (right === 0n) performEffect('divide-by-zero', { operator: 'mod' }, false);
      return new type(check(pyMod(left, right), 'mod'));
    },
    rem: (a: QyValue, b: QyValue): QyValue => {
      const left = requireTyped(a, 'rem');
      const right = requireTyped(b, 'rem');
      if (right === 0n) performEffect('divide-by-zero', { operator: 'rem' }, false);
      // BigInt `%` 向零截断（结果符号跟随被除数），与 `qy.num` 的 `remainder` 一致。
      return new type(check(left % right, 'rem'));
    },
    '<': (a: QyValue, b: QyValue): QyValue => (requireTyped(a, '<') < requireTyped(b, '<') ? QY_T : QY_NIL),
    '>': (a: QyValue, b: QyValue): QyValue => (requireTyped(a, '>') > requireTyped(b, '>') ? QY_T : QY_NIL),
    '<=': (a: QyValue, b: QyValue): QyValue => (requireTyped(a, '<=') <= requireTyped(b, '<=') ? QY_T : QY_NIL),
    '>=': (a: QyValue, b: QyValue): QyValue => (requireTyped(a, '>=') >= requireTyped(b, '>=') ? QY_T : QY_NIL),
    '=': (a: QyValue, b: QyValue): QyValue =>
      a instanceof type && b instanceof type && integerPayload(a) === integerPayload(b) ? QY_T : QY_NIL,
    'bit-and': (...args: QyValue[]): QyValue => {
      if (args.length === 0) return new type(-1n);
      let result = requireTyped(args[0], 'bit-and');
      for (const arg of args.slice(1)) result &= requireTyped(arg, 'bit-and');
      return new type(result);
    },
    'bit-or': (...args: QyValue[]): QyValue => {
      if (args.length === 0) return new type(0n);
      let result = requireTyped(args[0], 'bit-or');
      for (const arg of args.slice(1)) result |= requireTyped(arg, 'bit-or');
      return new type(result);
    },
    'bit-xor': (...args: QyValue[]): QyValue => {
      if (args.length === 0) return new type(0n);
      let result = requireTyped(args[0], 'bit-xor');
      for (const arg of args.slice(1)) result ^= requireTyped(arg, 'bit-xor');
      return new type(result);
    },
    'bit-not': (a: QyValue): QyValue => {
      const value = requireTyped(a, 'bit-not');
      const mask = (1n << BigInt(bits)) - 1n;
      let result = (~value) & mask;
      if (signed && result >= 1n << BigInt(bits - 1)) result -= 1n << BigInt(bits);
      return new type(result);
    },
    shl: (a: QyValue, b: QyValue): QyValue => new type(check(requireTyped(a, 'shl') << requireTyped(b, 'shl'), 'shl')),
    shr: (a: QyValue, b: QyValue): QyValue => new type(requireTyped(a, 'shr') >> requireTyped(b, 'shr')),
  };
  return {
    name,
    operators,
    values: { 'min-value': new type(min), 'max-value': new type(max), bits: new IntValue(BigInt(bits)) },
  };
}

function makeFloatSpace(name: string, type: FloatCtor, bits: number): NumberSpace {
  const requireTyped = (value: QyValue, op: string): number => {
    if (!(value instanceof FloatLikeValue) || (value.constructor as unknown) !== type) {
      throw new QyTypeError(`${name}.${op} expects ${name}`);
    }
    return floatPayload(value);
  };
  const finite = (value: number, op: string): number => checkFloatFinite(value, name, op);
  const operators: Record<string, Binding> = {
    [name]: (...args: QyValue[]): QyValue => {
      const value = args[0];
      let raw: number;
      if (value instanceof FloatLikeValue) raw = floatPayload(value);
      else if (value instanceof IntegerValue) raw = Number(integerPayload(value));
      else if (typeof value === 'number') raw = value;
      else throw new QyTypeError(`${name} constructor expects number`);
      return new type(finite(raw, 'constructor'));
    },
    [`${name}?`]: (value: QyValue): QyValue => (value instanceof type ? QY_T : QY_NIL),
    '+': (...args: QyValue[]): QyValue => {
      let total = 0;
      for (const arg of args) total += requireTyped(arg, '+');
      return new type(finite(total, '+'));
    },
    '-': (...args: QyValue[]): QyValue => {
      if (args.length === 1) return new type(-requireTyped(args[0], '-'));
      let result = requireTyped(args[0], '-');
      for (const arg of args.slice(1)) result -= requireTyped(arg, '-');
      return new type(finite(result, '-'));
    },
    '*': (...args: QyValue[]): QyValue => {
      let result = 1;
      for (const arg of args) result *= requireTyped(arg, '*');
      return new type(finite(result, '*'));
    },
    '/': (...args: QyValue[]): QyValue => {
      let result: number;
      if (args.length === 1) {
        const first = requireTyped(args[0], '/');
        if (first === 0) performEffect('divide-by-zero', { operator: '/' }, false);
        result = 1 / first;
      } else {
        result = requireTyped(args[0], '/');
        for (const arg of args.slice(1)) {
          const divisor = requireTyped(arg, '/');
          if (divisor === 0) performEffect('divide-by-zero', { operator: '/' }, false);
          result /= divisor;
        }
      }
      return new type(finite(result, '/'));
    },
    '<': (a: QyValue, b: QyValue): QyValue => (requireTyped(a, '<') < requireTyped(b, '<') ? QY_T : QY_NIL),
    '>': (a: QyValue, b: QyValue): QyValue => (requireTyped(a, '>') > requireTyped(b, '>') ? QY_T : QY_NIL),
    '<=': (a: QyValue, b: QyValue): QyValue => (requireTyped(a, '<=') <= requireTyped(b, '<=') ? QY_T : QY_NIL),
    '>=': (a: QyValue, b: QyValue): QyValue => (requireTyped(a, '>=') >= requireTyped(b, '>=') ? QY_T : QY_NIL),
    '=': (a: QyValue, b: QyValue): QyValue =>
      a instanceof type && b instanceof type && floatPayload(a) === floatPayload(b) ? QY_T : QY_NIL,
  };
  return { name, operators, values: { bits: new IntValue(BigInt(bits)) } };
}

/** qy.int8..qy.float128 全部模块（名称 → 绑定）。 */
export function numberSpaceModules(): NumberSpace[] {
  return [
    makeIntegerSpace('int8', Int8Value, 8, -128n, 127n),
    makeIntegerSpace('int16', Int16Value, 16, -32768n, 32767n),
    makeIntegerSpace('int32', Int32Value, 32, -2147483648n, 2147483647n),
    makeIntegerSpace('int64', Int64Value, 64, -9223372036854775808n, 9223372036854775807n),
    makeIntegerSpace('uint8', UInt8Value, 8, 0n, 255n),
    makeIntegerSpace('uint16', UInt16Value, 16, 0n, 65535n),
    makeIntegerSpace('uint32', UInt32Value, 32, 0n, 4294967295n),
    makeIntegerSpace('uint64', UInt64Value, 64, 0n, 18446744073709551615n),
    makeFloatSpace('float16', Float16Value, 16),
    makeFloatSpace('float32', Float32Value, 32),
    makeFloatSpace('float64', FloatValue, 64),
    makeFloatSpace('float128', Float128Value, 128),
  ];
}
