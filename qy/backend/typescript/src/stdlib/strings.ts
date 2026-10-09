// `qy.str` 模块算子。
//
// 真源：`qy/std/strings.py`。字符串输入同时接受 StringValue 与宿主 str
// （Python 侧 `_extract_str` 的迁移期互操作），但输出一律是 StringValue。

import { EvaluationError, QyRuntimeError, QyTypeError } from '../errors.ts';
import {
  CharValue,
  IntValue,
  ListValue,
  QY_NIL,
  QY_T,
  StringValue,
  Symbol,
  TupleValue,
  type QyValue,
} from '../values.ts';

function optional(value: QyValue): QyValue | null {
  return value === QY_NIL ? null : value;
}

function extractStr(value: QyValue, op: string): string {
  if (value instanceof StringValue) return value.value;
  if (typeof value === 'string') return value;
  if (value instanceof Symbol) return value.name;
  throw new QyTypeError(`${op}: expected string`);
}

function extractInt(value: QyValue, op: string): number {
  // 整型载荷是 BigInt，切片/索引位置还原为宿主 number（与 Python `_extract_int`
  // 返回 `int` 后再交给 `str` 切片等价）。
  if (value instanceof IntValue) return Number(value.value);
  if (typeof value === 'number' && Number.isInteger(value)) return value;
  throw new QyTypeError(`${op}: expected integer`);
}

export function stringLength(value: QyValue): QyValue {
  return new IntValue([...extractStr(value, 'string-length')].length);
}

export function stringConcat(...values: QyValue[]): QyValue {
  return new StringValue(values.map((value) => extractStr(value, 'string-concat')).join(''));
}

export function stringEq(a: QyValue, b: QyValue): QyValue {
  return extractStr(a, 'string=') === extractStr(b, 'string=') ? QY_T : QY_NIL;
}

// JS 字符串是 UTF-16 code unit 序列；Qy 的字符串索引是 **code point**（与 Python/Go 一致）。
function codePoints(text: string): string[] {
  return [...text];
}

export function stringSlice(value: QyValue, start: QyValue, end: QyValue = QY_NIL): QyValue {
  const chars = codePoints(extractStr(value, 'string-slice'));
  const i = extractInt(start, 'string-slice');
  const endOptional = optional(end);
  if (endOptional === null) return new StringValue(chars.slice(i).join(''));
  return new StringValue(chars.slice(i, extractInt(endOptional, 'string-slice')).join(''));
}

export function stringAt(value: QyValue, index: QyValue): QyValue {
  const chars = codePoints(extractStr(value, 'string-at'));
  const i = extractInt(index, 'string-at');
  if (i < 0 || i >= chars.length) {
    throw new EvaluationError(`string-at: index ${i} out of range for string of length ${chars.length}`);
  }
  return new CharValue(chars[i]);
}

export function stringFind(value: QyValue, needle: QyValue): QyValue {
  const text = extractStr(value, 'string-find');
  const utf16Index = text.indexOf(extractStr(needle, 'string-find'));
  // 把 UTF-16 code unit 索引转换为 code point 索引。
  return utf16Index === -1 ? QY_NIL : new IntValue(codePoints(text.slice(0, utf16Index)).length);
}

export function stringSplit(value: QyValue, separator: QyValue = QY_NIL): QyValue {
  const text = extractStr(value, 'string-split');
  const sep = optional(separator);
  if (sep !== null && extractStr(sep, 'string-split') === '') {
    // Python `str.split("")` 抛 `empty separator`：三宿主一致报错。
    throw new QyRuntimeError('empty separator');
  }
  const parts = sep === null ? text.split(/\s+/).filter((part) => part !== '') : text.split(extractStr(sep, 'string-split'));
  return new TupleValue(parts.map((part) => new StringValue(part)));
}

export function stringJoin(separator: QyValue, ...values: QyValue[]): QyValue {
  const sep = extractStr(separator, 'string-join');
  const parts: string[] = [];
  for (const value of values) {
    if (value instanceof TupleValue || value instanceof ListValue) {
      parts.push(...value.items.map((item) => extractStr(item, 'string-join')));
    } else if (Array.isArray(value)) {
      parts.push(...value.map((item) => extractStr(item, 'string-join')));
    } else {
      parts.push(extractStr(value, 'string-join'));
    }
  }
  return new StringValue(parts.join(sep));
}

export function stringReplace(value: QyValue, old: QyValue, replacement: QyValue): QyValue {
  const text = extractStr(value, 'string-replace');
  const from = extractStr(old, 'string-replace');
  const to = extractStr(replacement, 'string-replace');
  if (from === '') {
    // Python `str.replace("", to)` 在每个 code point 之间（含首尾）插入 to。
    return new StringValue(['', ...codePoints(text), ''].join(to));
  }
  return new StringValue(text.split(from).join(to));
}

export function stringEmpty(value: QyValue): QyValue {
  return extractStr(value, 'string-empty?') === '' ? QY_T : QY_NIL;
}

export function stringStartsWith(value: QyValue, prefix: QyValue): QyValue {
  return extractStr(value, 'string-starts-with?').startsWith(extractStr(prefix, 'string-starts-with?'))
    ? QY_T
    : QY_NIL;
}

export function stringEndsWith(value: QyValue, suffix: QyValue): QyValue {
  return extractStr(value, 'string-ends-with?').endsWith(extractStr(suffix, 'string-ends-with?'))
    ? QY_T
    : QY_NIL;
}

export function stringContains(value: QyValue, needle: QyValue): QyValue {
  return extractStr(value, 'string-contains?').includes(extractStr(needle, 'string-contains?'))
    ? QY_T
    : QY_NIL;
}

export function stringUpper(value: QyValue): QyValue {
  return new StringValue(extractStr(value, 'string-upper').toUpperCase());
}

export function stringLower(value: QyValue): QyValue {
  return new StringValue(extractStr(value, 'string-lower').toLowerCase());
}

export function stringTrim(value: QyValue): QyValue {
  return new StringValue(extractStr(value, 'string-trim').trim());
}

export function stringToList(value: QyValue): QyValue {
  return new TupleValue([...extractStr(value, 'string->list')].map((char) => new CharValue(char)));
}

export function stringToSymbol(value: QyValue): QyValue {
  return new Symbol(extractStr(value, 'string->symbol'));
}

export function symbolToString(value: QyValue): QyValue {
  if (value instanceof Symbol) return new StringValue(value.name);
  throw new QyTypeError('symbol->string: expected symbol');
}

export function stringBindings(): Record<string, QyValue> {
  return {
    'string?': (...args: QyValue[]) => (args[0] instanceof StringValue || typeof args[0] === 'string' ? QY_T : QY_NIL),
    'string-length': (...args: QyValue[]) => stringLength(args[0]),
    'string-concat': (...args: QyValue[]) => stringConcat(...args),
    'string=': (...args: QyValue[]) => stringEq(args[0], args[1]),
    'string-slice': (...args: QyValue[]) => stringSlice(args[0], args[1], args[2] ?? QY_NIL),
    'string-at': (...args: QyValue[]) => stringAt(args[0], args[1]),
    'string-find': (...args: QyValue[]) => stringFind(args[0], args[1]),
    'string-split': (...args: QyValue[]) => stringSplit(args[0], args[1] ?? QY_NIL),
    'string-join': (...args: QyValue[]) => stringJoin(args[0], ...args.slice(1)),
    'string-replace': (...args: QyValue[]) => stringReplace(args[0], args[1], args[2]),
    'string-empty?': (...args: QyValue[]) => stringEmpty(args[0]),
    'string-starts-with?': (...args: QyValue[]) => stringStartsWith(args[0], args[1]),
    'string-ends-with?': (...args: QyValue[]) => stringEndsWith(args[0], args[1]),
    'string-contains?': (...args: QyValue[]) => stringContains(args[0], args[1]),
    'string-upper': (...args: QyValue[]) => stringUpper(args[0]),
    'string-lower': (...args: QyValue[]) => stringLower(args[0]),
    'string-trim': (...args: QyValue[]) => stringTrim(args[0]),
    'string->list': (...args: QyValue[]) => stringToList(args[0]),
    'string->symbol': (...args: QyValue[]) => stringToSymbol(args[0]),
    'symbol->string': (...args: QyValue[]) => symbolToString(args[0]),
  };
}
