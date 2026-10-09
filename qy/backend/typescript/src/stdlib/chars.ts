// qy.char 模块算子（对应 `qy/std/chars.py`）。

import { QyRuntimeError, QyTypeError } from '../errors.ts';
import { CharValue, IntValue, QY_NIL, QY_T, StringValue, type QyValue } from '../values.ts';

type EagerBinding = (...args: QyValue[]) => QyValue;

function requireChar(value: QyValue, op: string): CharValue {
  if (value instanceof CharValue) return value;
  throw new QyTypeError(`${op}: expected char`);
}

function codePoint(value: QyValue, op: string): number {
  return requireChar(value, op).value.codePointAt(0) as number;
}

function charPredicate(value: QyValue): QyValue {
  return value instanceof CharValue ? QY_T : QY_NIL;
}

function charCompare(a: QyValue, b: QyValue, op: string, cmp: (x: number, y: number) => boolean): QyValue {
  return cmp(codePoint(a, op), codePoint(b, op)) ? QY_T : QY_NIL;
}

function charToInteger(c: QyValue): QyValue {
  return new IntValue(BigInt(codePoint(c, 'char->integer')));
}

function integerToChar(n: QyValue): QyValue {
  let code: number;
  if (n instanceof IntValue) code = Number(n.value);
  else if (typeof n === 'number') code = n;
  else throw new QyTypeError('integer->char: expected integer');
  if (!Number.isInteger(code) || code < 0 || code > 0x10ffff || (code >= 0xd800 && code <= 0xdfff)) {
    throw new QyTypeError(`integer->char: invalid codepoint ${code}`);
  }
  return new CharValue(String.fromCodePoint(code));
}

function charAlphabetic(c: QyValue): QyValue {
  return /\p{L}/u.test(requireChar(c, 'char-alphabetic?').value) ? QY_T : QY_NIL;
}

function charNumeric(c: QyValue): QyValue {
  return /\p{Nd}/u.test(requireChar(c, 'char-numeric?').value) ? QY_T : QY_NIL;
}

function charWhitespace(c: QyValue): QyValue {
  return /\s/u.test(requireChar(c, 'char-whitespace?').value) ? QY_T : QY_NIL;
}

function charUpperCase(c: QyValue): QyValue {
  return /\p{Lu}/u.test(requireChar(c, 'char-upper-case?').value) ? QY_T : QY_NIL;
}

function charLowerCase(c: QyValue): QyValue {
  return /\p{Ll}/u.test(requireChar(c, 'char-lower-case?').value) ? QY_T : QY_NIL;
}

function charUpcase(c: QyValue): QyValue {
  const mapped = requireChar(c, 'char-upcase').value.toUpperCase();
  if ([...mapped].length !== 1) {
    throw new QyRuntimeError('char value must contain exactly one Unicode scalar');
  }
  return new CharValue(mapped);
}

function charDowncase(c: QyValue): QyValue {
  const mapped = requireChar(c, 'char-downcase').value.toLowerCase();
  if ([...mapped].length !== 1) {
    throw new QyRuntimeError('char value must contain exactly one Unicode scalar');
  }
  return new CharValue(mapped);
}

function charToString(c: QyValue): QyValue {
  return new StringValue(requireChar(c, 'char->string').value);
}

export function charBindings(): Record<string, EagerBinding> {
  return {
    'char?': charPredicate,
    'char=?': (a, b) => charCompare(a, b, 'char=?', (x, y) => x === y),
    'char<?': (a, b) => charCompare(a, b, 'char<?', (x, y) => x < y),
    'char<=?': (a, b) => charCompare(a, b, 'char<=?', (x, y) => x <= y),
    'char>?': (a, b) => charCompare(a, b, 'char>?', (x, y) => x > y),
    'char>=?': (a, b) => charCompare(a, b, 'char>=?', (x, y) => x >= y),
    'char->integer': charToInteger,
    'integer->char': integerToChar,
    'char-alphabetic?': charAlphabetic,
    'char-numeric?': charNumeric,
    'char-whitespace?': charWhitespace,
    'char-upper-case?': charUpperCase,
    'char-lower-case?': charLowerCase,
    'char-upcase': charUpcase,
    'char-downcase': charDowncase,
    'char->string': charToString,
  };
}
