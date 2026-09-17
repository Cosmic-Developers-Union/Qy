// `qy.core` 的 chain / 容器 / 谓词算子。
//
// 真源：`qy/std/data.py`。这里只实现语料实际触达以及 CALL_BUILTIN ABI 需要的部分，
// 但把同族算子（car/cdr/cons/eq/len/atom/reify/get/has?/is/type/容器构造）一并补齐，
// 以便宿主嵌入时有完整的数据操作面。

import { QyArityError, QyReifyError, QyTypeError } from '../errors.ts';
import { defaultLiteralType, tryDefaultLiteral } from '../environment.ts';
import { MISSING } from '../internal.ts';
import {
  Chain,
  CharValue,
  DictValue,
  IntValue,
  ListValue,
  NoneValue,
  NumberValue,
  QY_NIL,
  QY_NONE,
  QY_T,
  SetValue,
  StringValue,
  Symbol,
  TupleValue,
  chainToList,
  isChain,
  isNil,
  listToChain,
  type QyValue,
} from '../values.ts';

function isQyChain(value: QyValue): boolean {
  return isNil(value) || isChain(value);
}

function properChainItems(value: QyValue, context: string): QyValue[] {
  try {
    return chainToList(value);
  } catch (error) {
    throw new QyTypeError(`${context} expects a proper Qy chain`);
  }
}

/** `atom`：不是非空 chain/tuple 时为真。 */
export function atom(value: QyValue): QyValue {
  if (isNil(value)) return QY_T;
  if (isChain(value)) return QY_NIL;
  if (value instanceof TupleValue) return value.length === 0 ? QY_T : QY_NIL;
  if (Array.isArray(value)) return value.length === 0 ? QY_T : QY_NIL;
  return QY_T;
}

/** `is`：identity 比较。 */
export function isIdentical(left: QyValue, right: QyValue): QyValue {
  return left === right ? QY_T : QY_NIL;
}

/** `eq`：Lisp 风格 eq（原子按值、引用类型按 identity 类型检查）。 */
export function eq(left: QyValue, right: QyValue): QyValue {
  if (isNil(left) && isNil(right)) return QY_T;
  if (left === QY_T && right === QY_T) return QY_T;
  if (left instanceof NoneValue && right instanceof NoneValue) return QY_T;
  if ((left as object | null)?.constructor !== (right as object | null)?.constructor) return QY_NIL;
  if (left instanceof NumberValue && right instanceof NumberValue) {
    return left.value === right.value ? QY_T : QY_NIL;
  }
  if (left instanceof StringValue && right instanceof StringValue) {
    return left.value === right.value ? QY_T : QY_NIL;
  }
  if (typeof left === 'string' && typeof right === 'string') {
    return left === right ? QY_T : QY_NIL;
  }
  if (left instanceof Symbol && right instanceof Symbol) {
    return left.name === right.name ? QY_T : QY_NIL;
  }
  return QY_NIL;
}

/** `same_qy_key`：容器 key 比较（跨宿主 str / NumberValue 也成立）。 */
export function sameQyKey(left: QyValue, right: QyValue): boolean {
  if (left instanceof StringValue && typeof right === 'string') return left.value === right;
  if (typeof left === 'string' && right instanceof StringValue) return left === right.value;
  if (typeof left === 'string' && typeof right === 'string') return left === right;
  if (left instanceof NumberValue && typeof right === 'number' && typeof right !== 'boolean') {
    return left.value === right;
  }
  if (right instanceof NumberValue && typeof left === 'number' && typeof left !== 'boolean') {
    return left === right.value;
  }
  if (typeof left === 'boolean' || typeof right === 'boolean') return left === right;
  return eq(left, right) === QY_T;
}

/** `car`。 */
export function carOp(value: QyValue): QyValue {
  if (isNil(value)) return QY_NIL;
  if (isChain(value)) return value.head;
  throw new QyTypeError(`car expects a chain, got ${String(value)}`);
}

/** `cdr`。 */
export function cdrOp(value: QyValue): QyValue {
  if (isNil(value)) return QY_NIL;
  if (isChain(value)) return value.tail;
  throw new QyTypeError(`cdr expects a chain, got ${String(value)}`);
}

/** `cons`。 */
export function consOp(head: QyValue, tail: QyValue): QyValue {
  return new Chain(head, tail);
}

/** `chain`：tuple/list → chain。 */
export function chainOp(value: QyValue): QyValue {
  if (isNil(value) || isChain(value)) return value;
  if (value instanceof TupleValue || value instanceof ListValue) return listToChain(value.items);
  throw new QyTypeError('chain expects a tuple/list container');
}

function appendItems(value: QyValue): QyValue[] {
  if (value instanceof TupleValue || value instanceof ListValue) return value.items;
  if (isNil(value)) return [];
  if (isChain(value)) return properChainItems(value, 'append');
  throw new QyTypeError('append expects tuple/list/chain inputs');
}

/** `append`。 */
export function appendOp(left: QyValue, right: QyValue): QyValue {
  const combined = [...appendItems(left), ...appendItems(right)];
  if (isChain(left) || isNil(left) || isChain(right) || isNil(right)) return listToChain(combined);
  if (left instanceof ListValue || right instanceof ListValue) return new ListValue(combined);
  return new TupleValue(combined);
}

/** `len`。 */
export function lenOp(value: QyValue): QyValue {
  if (value instanceof Symbol) return new IntValue([...value.name].length);
  if (isNil(value)) return new IntValue(0);
  if (isChain(value)) {
    try {
      return new IntValue(chainToList(value).length);
    } catch {
      throw new QyTypeError('len expects a proper Qy chain');
    }
  }
  if (value instanceof StringValue) return new IntValue([...value.value].length);
  if (
    value instanceof TupleValue ||
    value instanceof ListValue ||
    value instanceof DictValue ||
    value instanceof SetValue
  ) {
    return new IntValue(value.length);
  }
  throw new QyTypeError('len expects a collection');
}

/** `get`：dict / tuple / list / chain 取项。 */
export function getOp(collection: QyValue, key: QyValue, ...defaults: QyValue[]): QyValue {
  if (defaults.length > 1) {
    throw new QyArityError(`get expects two or three arguments, got ${defaults.length + 2}`);
  }
  const fallback = defaults.length > 0 ? defaults[0] : QY_NONE;
  if (collection instanceof DictValue) {
    for (const [entryKey, item] of collection.entries) {
      if (sameQyKey(entryKey, key)) return item;
    }
    return fallback;
  }
  if (collection instanceof TupleValue || collection instanceof ListValue) {
    const index = ensureIndex(key);
    return index >= -collection.items.length && index < collection.items.length
      ? collection.items.at(index)
      : fallback;
  }
  if (isNil(collection)) return fallback;
  if (isChain(collection)) {
    const index = ensureIndex(key);
    const items = chainToList(collection);
    return index >= -items.length && index < items.length ? items.at(index) : fallback;
  }
  throw new QyTypeError('get expects a chain, tuple, list, or dict');
}

function ensureIndex(value: QyValue): number {
  if (value instanceof IntValue) return value.value;
  if (typeof value === 'number' && Number.isInteger(value)) return value;
  throw new QyTypeError('expected integer index');
}

/** `has?`。 */
export function hasOp(collection: QyValue, key: QyValue): QyValue {
  if (collection instanceof DictValue) {
    return collection.entries.some(([entryKey]) => sameQyKey(entryKey, key)) ? QY_T : QY_NIL;
  }
  if (collection instanceof SetValue) {
    return collection.items.some((item) => sameQyKey(item, key)) ? QY_T : QY_NIL;
  }
  if (collection instanceof TupleValue || collection instanceof ListValue) {
    const index = ensureIndex(key);
    const length = collection.items.length;
    return index >= -length && index < length ? QY_T : QY_NIL;
  }
  if (isNil(collection)) return QY_NIL;
  if (isChain(collection)) {
    const index = ensureIndex(key);
    const length = chainToList(collection).length;
    return index >= -length && index < length ? QY_T : QY_NIL;
  }
  throw new QyTypeError('has? expects a chain, tuple, list, dict, or set');
}

/** `tuple` / `list` / `dict` / `set` 构造。 */
export function tupleOp(...args: QyValue[]): QyValue {
  if (args.length === 1 && isQyChain(args[0])) return new TupleValue(properChainItems(args[0], 'tuple'));
  return new TupleValue(args);
}

export function listOp(...args: QyValue[]): QyValue {
  if (args.length === 1 && isQyChain(args[0])) return new ListValue(properChainItems(args[0], 'list'));
  return new ListValue(args);
}

export function dictOp(...args: QyValue[]): QyValue {
  if (args.length === 1 && isQyChain(args[0])) {
    const entries: [QyValue, QyValue][] = [];
    for (const entry of properChainItems(args[0], 'dict')) {
      entries.push(dictEntryPair(entry));
    }
    return new DictValue(entries);
  }
  if (args.length % 2 !== 0) {
    throw new QyArityError(`dict expects key/value pairs, got ${args.length} argument(s)`);
  }
  const entries: [QyValue, QyValue][] = [];
  for (let index = 0; index < args.length; index += 2) {
    const key = args[index];
    const value = args[index + 1];
    const existing = entries.findIndex(([entryKey]) => sameQyKey(entryKey, key));
    if (existing >= 0) entries[existing] = [key, value];
    else entries.push([key, value]);
  }
  return new DictValue(entries);
}

function dictEntryPair(entry: QyValue): [QyValue, QyValue] {
  if (isChain(entry)) {
    const tail = (entry as Chain).tail;
    if (!isNil(tail) && !isChain(tail)) return [(entry as Chain).head, tail];
    const items = properChainItems(entry, 'dict entry');
    if (items.length !== 2) throw new QyTypeError('dict chain entry must contain two values');
    return [items[0], items[1]];
  }
  if (Array.isArray(entry)) {
    if (entry.length !== 2) throw new QyTypeError('dict chain entry must contain two values');
    return [entry[0], entry[1]];
  }
  throw new QyTypeError('dict chain entry must be a pair');
}

export function setOp(...args: QyValue[]): QyValue {
  const values = args.length === 1 && isQyChain(args[0]) ? properChainItems(args[0], 'set') : args;
  const items: QyValue[] = [];
  for (const value of values) {
    if (!items.some((existing) => sameQyKey(existing, value))) items.push(value);
  }
  return new SetValue(items);
}

export function tuplePredicate(value: QyValue): QyValue {
  return value instanceof TupleValue ? QY_T : QY_NIL;
}
export function listPredicate(value: QyValue): QyValue {
  return value instanceof ListValue ? QY_T : QY_NIL;
}
export function dictPredicate(value: QyValue): QyValue {
  return value instanceof DictValue ? QY_T : QY_NIL;
}
export function setPredicate(value: QyValue): QyValue {
  return value instanceof SetValue ? QY_T : QY_NIL;
}

/** `type`：Qy 语义类型名（不泄漏宿主类名）。 */
export function typeOp(value: QyValue): QyValue {
  if (isNil(value)) return new Symbol('nil');
  if (value === QY_T) return new Symbol('T');
  if (value instanceof NoneValue) return new Symbol('none');
  if (isChain(value)) return new Symbol('chain');
  if (value instanceof Symbol) return new Symbol('symbol');
  if (value instanceof TupleValue) return new Symbol('tuple');
  if (value instanceof ListValue) return new Symbol('list');
  if (value instanceof DictValue) return new Symbol('dict');
  if (value instanceof SetValue) return new Symbol('set');
  if (value instanceof NumberValue) return new Symbol('number');
  if (value instanceof StringValue) return new Symbol('string');
  if (value instanceof CharValue) return new Symbol('char');
  return new Symbol('object');
}

/**
 * `reify`：runtime 值 → syntax datum。
 *
 * 这是 ScopeOperator（`_reify(args, env)`），所以由 RawOperatorValue 承载。
 * 对应 `qy/std/data.py::_reify`。
 */
export function reifyOp(args: QyValue[], _env: QyValue): QyValue {
  if (args.length !== 1) {
    throw new QyReifyError(`reify expects exactly 1 argument, got ${args.length}`);
  }
  return reifyValue(args[0]);
}

/** 单个值的 reify（含 chain 递归）。 */
export function reifyValue(value: QyValue): QyValue {
  if (isNil(value)) return new Symbol('nil');
  if (value === QY_T) return new Symbol('T');
  if (value instanceof NoneValue) return new Symbol('none');
  if (value instanceof Symbol) return value;
  if (value instanceof NumberValue) return new Symbol(String(value.value));
  if (typeof value === 'number') return new Symbol(String(value));
  if (value instanceof StringValue) return new Symbol(`"${value.value}"`);
  if (typeof value === 'string') return new Symbol(`"${value}"`);
  if (value instanceof CharValue) return new Symbol(`#\\${value.value}`);
  if (isChain(value)) {
    const items: QyValue[] = [];
    let node: QyValue = value;
    while (isChain(node)) {
      items.push(reifyValue((node as Chain).head));
      node = (node as Chain).tail;
    }
    if (isNil(node)) return listToChain(items);
    const tail = reifyValue(node);
    if (isChain(tail) || isNil(tail)) return listToChain([...items, ...chainToList(tail)]);
    return new Chain(items.length > 0 ? listToChain(items) : QY_NIL, tail);
  }
  throw new QyReifyError(`cannot reify value of type ${(value as { typeName?: string })?.typeName ?? 'object'}`);
}

/** APPLY / `apply` 的实参归一：字面量拼写（Symbol）在 VM 里还原为字面量值。 */
export function normalizeArgument(value: QyValue): QyValue {
  if (value instanceof Symbol && defaultLiteralType(value.name) !== null) {
    const literal = tryDefaultLiteral(value);
    if (literal !== MISSING) return literal;
  }
  return value;
}

/** `data.py` 的 chain/container 算子绑定。 */
export function dataBindings(): Record<string, QyValue> {
  return {
    atom: (...args: QyValue[]) => atom(args[0]),
    car: (...args: QyValue[]) => carOp(args[0]),
    cdr: (...args: QyValue[]) => cdrOp(args[0]),
    chain: (...args: QyValue[]) => chainOp(args[0]),
    append: (...args: QyValue[]) => appendOp(args[0], args[1]),
    cons: (...args: QyValue[]) => consOp(args[0], args[1]),
    eq: (...args: QyValue[]) => eq(args[0], args[1]),
    'get': (...args: QyValue[]) => getOp(args[0], args[1], ...args.slice(2)),
    'has?': (...args: QyValue[]) => hasOp(args[0], args[1]),
    is: (...args: QyValue[]) => isIdentical(args[0], args[1]),
    len: (...args: QyValue[]) => lenOp(args[0]),
    type: (...args: QyValue[]) => typeOp(args[0]),
    tuple: (...args: QyValue[]) => tupleOp(...args),
    'tuple?': (...args: QyValue[]) => tuplePredicate(args[0]),
    list: (...args: QyValue[]) => listOp(...args),
    'list?': (...args: QyValue[]) => listPredicate(args[0]),
    dict: (...args: QyValue[]) => dictOp(...args),
    'dict?': (...args: QyValue[]) => dictPredicate(args[0]),
    set: (...args: QyValue[]) => setOp(...args),
    'set?': (...args: QyValue[]) => setPredicate(args[0]),
  };
}
