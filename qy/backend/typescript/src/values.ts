// Qy 运行时值模型。
//
// 真源：`qy/core/syntax.py`（Symbol / Chain / nil / T / none）与
// `qy/sem/core.py`（Value / NumberValue / StringValue / 容器）。
//
// 关键语义点（后面各模块都依赖）：
// - `nil` / `T` / `none` 是单例对象，不是宿主布尔/undefined；
// - 数值类型有 "concrete type" 身份：`(+ int32 int64)` 不隐式提升，
//   `=` 要求两侧 concrete number 类型相同（`qy/session/number_ops.py`）；
// - Symbol 不 interning：`=` 对非数值用 identity，`eq` 对 Symbol 用结构比较。

import { QyTypeError } from './errors.ts';

/** nil（空链）单例，对应 Python `qy.core.syntax.nil`。 */
export class NilValue {
  readonly typeName = 'nil';
  toString(): string {
    return 'nil';
  }
}
export const QY_NIL = new NilValue();

/** 真值 T 单例，对应 Python `TValue`。 */
export class TValue {
  readonly typeName = 't';
  toString(): string {
    return 'T';
  }
}
export const QY_T = new TValue();

/** none 单例，对应 Python `NoneValue`。 */
export class NoneValue {
  readonly typeName = 'none';
  toString(): string {
    return 'none';
  }
}
export const QY_NONE = new NoneValue();

/** Qy 语法 datum 的原子：一个符号拼写。对应 `qy.core.syntax.Symbol`。 */
export class Symbol {
  constructor(readonly name: string) {}
  toString(): string {
    return this.name;
  }
}

/** 不可变 cons cell。对应 `qy.core.syntax.Chain`。 */
export class Chain {
  constructor(
    readonly head: QyValue,
    readonly tail: QyValue,
  ) {}
}

/** 任何 Qy 运行时值的并集（宿主原语只作为过渡期互操作出现）。 */
export type QyValue = unknown;

// ---------------------------------------------------------------------------
// 数值值
// ---------------------------------------------------------------------------

/** 数值家族基类。对应 `qy.sem.core.NumberValue`。
 *
 * 重要：整型家族的 `value` 是 `bigint`，浮点家族是 `number`。
 * Python 侧 `IntValue.value` 是任意精度 int（`qy/sem/core.py:IntValue`），
 * 所以 TS 侧必须用 BigInt 才能与 Python 逐字节一致；用 double 会在
 * 2^53 之后静默算错。`number` 允许出现在构造参数里只是为了兼容宿主互操作
 * （宿主注入 `new IntValue(42)`），内部一律归一到 BigInt。
 */
export abstract class NumberValue {
  abstract readonly typeName: string;
  /** 是否是整型家族（决定 `str()` 与取模语义）。 */
  abstract readonly isInteger: boolean;
  constructor(readonly value: number | bigint) {}
}

/** 整型家族基类。 */
export abstract class IntegerValue extends NumberValue {
  readonly isInteger = true;
  declare readonly value: bigint;
  constructor(value: number | bigint | string) {
    super(typeof value === 'bigint' ? value : BigInt(value));
  }
}

/** 浮点家族基类。 */
export abstract class FloatLikeValue extends NumberValue {
  readonly isInteger = false;
  declare readonly value: number;
  constructor(value: number) {
    super(value);
  }
}

/** 取整型载荷（断言 `IntegerValue.value` 已经是 BigInt）。 */
export function integerPayload(value: NumberValue): bigint {
  return value.value as bigint;
}

/** 取浮点载荷。 */
export function floatPayload(value: NumberValue): number {
  return value.value as number;
}

/**
 * 数字载荷的跨表示相等比较（bigint/bigint、number/number、以及宿主 number）。
 * bigint 与 number 混比时按精确值比较，避免 `1n === 1` 恒为 false 的宿主陷阱。
 */
export function numberPayloadEquals(left: number | bigint, right: number | bigint): boolean {
  if (typeof left === 'bigint' && typeof right === 'bigint') return left === right;
  if (typeof left === 'number' && typeof right === 'number') return left === right;
  if (typeof left === 'bigint') return typeof right === 'number' && Number.isInteger(right) && BigInt(right) === left;
  return typeof left === 'number' && Number.isInteger(left) && BigInt(left) === right;
}

export class IntValue extends IntegerValue {
  readonly typeName = 'int';
}
export class Int8Value extends IntegerValue {
  readonly typeName = 'int8';
}
export class Int16Value extends IntegerValue {
  readonly typeName = 'int16';
}
export class Int32Value extends IntegerValue {
  readonly typeName = 'int32';
}
export class Int64Value extends IntegerValue {
  readonly typeName = 'int64';
}
export class UInt8Value extends IntegerValue {
  readonly typeName = 'uint8';
}
export class UInt16Value extends IntegerValue {
  readonly typeName = 'uint16';
}
export class UInt32Value extends IntegerValue {
  readonly typeName = 'uint32';
}
export class UInt64Value extends IntegerValue {
  readonly typeName = 'uint64';
}
export class FloatValue extends FloatLikeValue {
  readonly typeName = 'float';
}
export class Float16Value extends FloatLikeValue {
  readonly typeName = 'float16';
}
export class Float32Value extends FloatLikeValue {
  readonly typeName = 'float32';
}
export class Float128Value extends FloatLikeValue {
  readonly typeName = 'float128';
}

/** 复数（语义模型层面；数值运算不覆盖）。 */
export class ComplexValue extends NumberValue {
  readonly typeName = 'complex';
  readonly isInteger = false;
  constructor(
    readonly real: NumberValue,
    readonly imag: NumberValue,
  ) {
    super(Number.NaN);
  }
}

/** 有理数（语义模型层面）。 */
export class RationalValue extends NumberValue {
  readonly typeName = 'rational';
  readonly isInteger = true;
  constructor(
    readonly numerator: NumberValue,
    readonly denominator: NumberValue,
  ) {
    super(Number.NaN);
  }
}

// ---------------------------------------------------------------------------
// 字符串 / 字符 / 容器
// ---------------------------------------------------------------------------

/** 单字符值。对应 `qy.sem.core.CharValue`。 */
export class CharValue {
  readonly typeName = 'char';
  constructor(readonly value: string) {}
}

/** Qy 字符串值。对应 `qy.sem.core.StringValue`。 */
export class StringValue {
  readonly typeName = 'string';
  constructor(readonly value: string) {}
}

/** 不可变 tuple。对应 `qy.sem.core.TupleValue`。 */
export class TupleValue {
  readonly typeName = 'tuple';
  constructor(readonly items: QyValue[]) {}
  get length(): number {
    return this.items.length;
  }
}

/** Qy list。对应 `qy.sem.core.ListValue`。 */
export class ListValue {
  readonly typeName = 'list';
  constructor(readonly items: QyValue[]) {}
  get length(): number {
    return this.items.length;
  }
}

/** Qy dict（有序 entry）。 */
export class DictValue {
  readonly typeName = 'dict';
  constructor(readonly entries: [QyValue, QyValue][]) {}
  get length(): number {
    return this.entries.length;
  }
}

/** Qy set（有序去重项）。 */
export class SetValue {
  readonly typeName = 'set';
  constructor(readonly items: QyValue[]) {}
  get length(): number {
    return this.items.length;
  }
}

/** 连续内存段（语义模型层面）。 */
export class ArrayValue {
  readonly typeName = 'array';
  constructor(
    readonly elementType: string,
    readonly items: QyValue[],
  ) {}
  get length(): number {
    return this.items.length;
  }
}

/** hash-map 家族（语义模型层面）。 */
export class HashMapValue {
  readonly typeName = 'hash-map';
  constructor(readonly entries: [QyValue, QyValue][]) {}
  get length(): number {
    return this.entries.length;
  }
}

// ---------------------------------------------------------------------------
// 可调用值 / effect / module
// ---------------------------------------------------------------------------

/**
 * eager 参数算子值（对应 PureOperator）。`fn` 直接接收求值后的参数。
 *
 * 允许返回 Promise：宿主可以用 `registerHostFunction` 注册 async 函数
 * （VM 的 `call` 会 `await` 返回值），这是 `parallel` / `all` / `race`
 * 真正并发的前提。
 */
export class PureOperatorValue {
  constructor(
    readonly name: string,
    readonly fn: (...args: QyValue[]) => QyValue | Promise<QyValue>,
  ) {}
}

/**
 * raw 参数算子值（对应 Scope/Control/Effect/MetaOperator）。
 * `fn` 接收 (args, env)，与 Python `func(args, env)` 一致。
 */
export class RawOperatorValue {
  constructor(
    readonly name: string,
    readonly fn: (args: QyValue[], env: QyValue) => QyValue,
  ) {}
}

/** effect 定义值。对应 `qy.sem.runtime.EffectDefinition`。 */
export class EffectDefinition {
  constructor(
    readonly name: string,
    readonly resumable: boolean,
  ) {}
}

/** 续延值。对应 `qy.vm.instance.frame.QyContinuation`。 */
export class Continuation {
  constructor(
    readonly effect: string,
    readonly resumable: boolean,
    readonly resumeFn: (value: QyValue) => unknown,
  ) {}
  resume(value: QyValue): unknown {
    return this.resumeFn(value);
  }
}

/** 模块值。对应 `qy.import_.module.StandardModule`。 */
export class ModuleValue {
  constructor(
    readonly name: string,
    readonly exports: Map<string, QyValue>,
    readonly macroExports: Map<string, QyValue>,
  ) {}
  resolve(name: string): QyValue {
    if (this.exports.has(name)) return this.exports.get(name);
    return this.macroExports.get(name);
  }
}

/**
 * `MAKE_MACRO` 的编译期占位符。对应 Python 的 `_COMPILE_TIME_MACRO`。
 * 它不会被打印，也不会进入 APPEND_RESULT/RETURN 的结果。
 */
export const COMPILE_TIME_MACRO = globalThis.Symbol('__compile_time_macro__');

// ---------------------------------------------------------------------------
// 链工具函数（对应 qy.core.syntax 的 car/cdr/cons/chain_to_list/list_to_chain）
// ---------------------------------------------------------------------------

export function isNil(value: QyValue): boolean {
  return value instanceof NilValue;
}

export function isChain(value: QyValue): value is Chain {
  return value instanceof Chain;
}

export function cons(head: QyValue, tail: QyValue): Chain {
  return new Chain(head, tail);
}

export function carOf(value: QyValue): QyValue {
  if (value instanceof Chain) return value.head;
  throw new QyTypeError(`car expects a Chain, got ${describe(value)}`);
}

export function cdrOf(value: QyValue): QyValue {
  if (value instanceof Chain) return value.tail;
  throw new QyTypeError(`cdr expects a Chain, got ${describe(value)}`);
}

/** proper chain → 数组；improper chain 抛错（对应 `chain_to_list`）。 */
export function chainToList(value: QyValue): QyValue[] {
  if (isNil(value)) return [];
  const result: QyValue[] = [];
  let current: QyValue = value;
  while (current instanceof Chain) {
    result.push(current.head);
    current = current.tail;
  }
  if (!isNil(current)) {
    throw new QyTypeError('Cannot convert improper chain to list');
  }
  return result;
}

/** 数组 → proper chain。 */
export function listToChain(items: QyValue[]): QyValue {
  let result: QyValue = QY_NIL;
  for (let i = items.length - 1; i >= 0; i -= 1) {
    result = new Chain(items[i], result);
  }
  return result;
}

/** 简单描述，用于错误信息。 */
export function describe(value: QyValue): string {
  if (value instanceof NilValue) return 'nil';
  if (value instanceof TValue) return 'T';
  if (value instanceof NoneValue) return 'none';
  if (value instanceof Symbol) return value.name;
  if (value instanceof Chain) return '(chain)';
  if (value instanceof NumberValue) return String(value.value);
  if (value instanceof StringValue) return JSON.stringify(value.value);
  return String(value);
}
