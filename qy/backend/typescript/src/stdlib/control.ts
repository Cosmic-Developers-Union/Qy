// `qy.core` 的控制算子中属于运行期的部分。
//
// 真源：`qy/std/control.py`。`cond` / `let` / `define` / `defun` / `lambda` /
// `quote` / `macro` 都是编译期形式，不会出现在字节码运行期；
// 运行期真正被 LOAD_ENV 调用的是 `truthy`。

import { Env } from '../environment.ts';
import { QyTypeError } from '../errors.ts';
import {
  DictValue,
  ListValue,
  NoneValue,
  QY_NIL,
  QY_T,
  SLOT_TOKEN,
  SetValue,
  Symbol,
  TupleValue,
  isChain,
  isNil,
  type QyValue,
} from '../values.ts';

/**
 * `truthy`：标准 profile 的复合真值判断（`control.py::_complex_truthy`）。
 * nil / none / false / () / 0 / "" / 空容器都是假。
 */
export function truthy(value: QyValue): QyValue {
  if (isNil(value)) return QY_NIL;
  if (value === null || value === undefined) return QY_NIL;
  if (value instanceof NoneValue) return QY_NIL;
  if (value === false) return QY_NIL;
  if (Array.isArray(value) && value.length === 0) return QY_NIL;
  if (typeof value === 'number' && value === 0) return QY_NIL;
  // 注意：Python 只对宿主 str 判空（StringValue 不是 str 子类），
  // 因此 `(truthy "")` 在 Qy 语义下是 **真**（语料 39 依赖这一点）。
  if (typeof value === 'string' && value === '') return QY_NIL;
  if (
    (value instanceof TupleValue ||
      value instanceof ListValue ||
      value instanceof DictValue ||
      value instanceof SetValue) &&
    value.length === 0
  ) {
    return QY_NIL;
  }
  return QY_T;
}

/** 语言核的 nil-only 真值（`machine.py::_truthy`），JUMP_IF_FALSE 使用。 */
export function coreTruthy(value: QyValue): boolean {
  return !isNil(value);
}

/** `not`。 */
export function notOp(value: QyValue): QyValue {
  return coreTruthy(value) ? QY_NIL : QY_T;
}

/** `nil?`。 */
export function nilPredicate(value: QyValue): QyValue {
  return isNil(value) ? QY_T : QY_NIL;
}

export function controlBindings(): Record<string, QyValue> {
  return {
    truthy: (...args: QyValue[]) => truthy(args[0]),
    'nil?': (...args: QyValue[]) => nilPredicate(args[0]),
    not: (...args: QyValue[]) => notOp(args[0]),
  };
}

// -- symbol-space 显式建模算子（raw：需要当前 env） -------------------------

/** `this`：返回当前 symbol-space。 */
export function thisOp(_args: QyValue[], env: QyValue): QyValue {
  return env;
}

/** `slot`：创建绑定槽位占位符。 */
export function slotOp(): QyValue {
  return SLOT_TOKEN;
}

/** `bind`：把 symbol 与 value 绑定到指定 slot（slot 仅占位，绑定写入当前空间）。 */
export function bindOp(args: QyValue[], env: QyValue): QyValue {
  const name = args[0];
  const value = args[1];
  if (!(name instanceof Symbol)) {
    throw new QyTypeError('bind expects a symbol');
  }
  const symbol =
    name.name.startsWith("'") && name.name.length > 1 ? new Symbol(name.name.slice(1)) : name;
  if (!(env instanceof Env)) {
    throw new QyTypeError('bind expects a symbol-space');
  }
  env.define(symbol.name, value);
  return value;
}
