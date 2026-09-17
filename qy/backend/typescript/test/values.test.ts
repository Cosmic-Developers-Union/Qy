// 值模型与字面量解析的单元测试。
//
// 运行：bun test（在 qy/backend/typescript 下）

import { describe, expect, test } from 'bun:test';
import {
  CharValue,
  Chain,
  Continuation,
  FloatValue,
  IntValue,
  QY_NIL,
  QY_NONE,
  QY_T,
  StringValue,
  Symbol,
  TupleValue,
  chainToList,
  listToChain,
} from '../src/values.ts';
import {
  defaultLiteralType,
  isCharLiteral,
  isNumberLiteral,
  isStringLiteral,
  parseCharLiteral,
  parseStringLiteral,
  tryDefaultLiteral,
} from '../src/environment.ts';
import { MISSING } from '../src/internal.ts';
import { formatValue, pyFloatRepr } from '../src/display.ts';

describe('值模型', () => {
  test('单例与链工具', () => {
    expect(QY_NIL).not.toBe(QY_T);
    expect(QY_T).not.toBe(QY_NONE);
    const chain = listToChain([new IntValue(1), new IntValue(2), new IntValue(3)]);
    expect(chain).toBeInstanceOf(Chain);
    expect(chainToList(chain).map(formatValue)).toEqual(['1', '2', '3']);
    expect(chainToList(QY_NIL)).toEqual([]);
  });

  test('格式化与 display.py 对齐', () => {
    expect(formatValue(QY_NIL)).toBe('nil');
    expect(formatValue(QY_T)).toBe('T');
    expect(formatValue(QY_NONE)).toBe('none');
    expect(formatValue(new IntValue(42))).toBe('42');
    expect(formatValue(new StringValue('abc'))).toBe('abc');
    expect(formatValue(new TupleValue([new IntValue(1), new IntValue(2)]))).toBe('(1 2)');
    expect(formatValue(new Symbol('x'))).toBe('x');
    expect(formatValue(listToChain([new Symbol('quote'), new Symbol('x')]))).toBe('(quote x)');
    // improper chain
    expect(formatValue(new Chain(new IntValue(1), new IntValue(2)))).toBe('(1 . 2)');
  });

  test('Python 浮点 repr', () => {
    expect(pyFloatRepr(4)).toBe('4.0');
    expect(pyFloatRepr(3.14)).toBe('3.14');
    expect(pyFloatRepr(-0.5)).toBe('-0.5');
    expect(pyFloatRepr(1e16)).toBe('1e+16');
    expect(pyFloatRepr(1e-7)).toBe('1e-07');
  });
});

describe('字面量解析（pre_ss）', () => {
  test('数字', () => {
    expect(isNumberLiteral('42')).toBe(true);
    expect(isNumberLiteral('2.5')).toBe(true);
    expect(isNumberLiteral('-3')).toBe(true);
    expect(isNumberLiteral('abc')).toBe(false);
    // Python int() 默认进制不接受 0x 前缀
    expect(isNumberLiteral('0x10')).toBe(false);
    const value = tryDefaultLiteral(new Symbol('42'));
    expect(value).toBeInstanceOf(IntValue);
    expect((value as IntValue).value).toBe(42);
    expect(tryDefaultLiteral(new Symbol('2.5'))).toBeInstanceOf(FloatValue);
  });

  test('字符串', () => {
    expect(isStringLiteral('"abc"')).toBe(true);
    const value = tryDefaultLiteral(new Symbol('"a\\nb"'));
    expect(value).toBeInstanceOf(StringValue);
    expect((value as StringValue).value).toBe('a\nb');
    expect((parseStringLiteral('r"a\\nb"') as StringValue).value).toBe('a\\nb');
  });

  test('字符 / lisp 值', () => {
    expect(isCharLiteral('#\\a')).toBe(true);
    expect((parseCharLiteral('#\\space') as CharValue).value).toBe(' ');
    expect((tryDefaultLiteral(new Symbol('#\\u0041')) as CharValue).value).toBe('A');
    expect(tryDefaultLiteral(new Symbol('nil'))).toBe(QY_NIL);
    expect(tryDefaultLiteral(new Symbol('T'))).toBe(QY_T);
    expect(tryDefaultLiteral(new Symbol('false'))).toBe(QY_NIL);
    expect(tryDefaultLiteral(new Symbol('none'))).toBe(QY_NONE);
    expect(tryDefaultLiteral(new Symbol('nope'))).toBe(MISSING);
  });

  test('default_literal_type', () => {
    expect(defaultLiteralType('"x"')).toBe('string');
    expect(defaultLiteralType('7')).toBe('number');
    expect(defaultLiteralType('nil')).toBe('nil');
    expect(defaultLiteralType('x')).toBe(null);
  });
});

describe('effect 值', () => {
  test('continuation 默认 identity', () => {
    const continuation = new Continuation('e', true, (value) => value);
    expect(continuation.resume(new IntValue(1))).toBeInstanceOf(IntValue);
  });
});
