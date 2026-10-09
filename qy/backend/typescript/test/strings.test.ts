// `qy.str` 字符串算子的单元测试：code point 索引与 Python `str.replace` 语义。
//
// 运行：bun test（在 qy/backend/typescript 下）

import { describe, expect, test } from 'bun:test';
import { stringBindings } from '../src/stdlib/strings.ts';
import { formatValue } from '../src/display.ts';
import { CharValue, IntValue, StringValue, TupleValue } from '../src/values.ts';

const ops = stringBindings();
const call = (name: string, ...args: unknown[]): unknown =>
  (ops[name] as (...a: unknown[]) => unknown)(...args);
const text = (value: unknown): string => (value as StringValue).value;

describe('qy.str code-point indexing', () => {
  test('string-length counts code points, not UTF-16 units', () => {
    expect(formatValue(call('string-length', new StringValue('😀')))).toBe('1');
    expect(formatValue(call('string-length', new StringValue('a😀b')))).toBe('3');
  });

  test('string-slice slices by code point', () => {
    expect(text(call('string-slice', new StringValue('😀ab'), new IntValue(0n), new IntValue(1n)))).toBe('😀');
    expect(text(call('string-slice', new StringValue('😀ab'), new IntValue(1n), new IntValue(2n)))).toBe('a');
    expect(text(call('string-slice', new StringValue('😀ab'), new IntValue(1n)))).toBe('ab');
  });

  test('string-at returns a whole code point', () => {
    const value = call('string-at', new StringValue('😀'), new IntValue(0n));
    expect(value).toBeInstanceOf(CharValue);
    expect((value as CharValue).value).toBe('😀');
  });

  test('string-find returns a code-point index', () => {
    expect(formatValue(call('string-find', new StringValue('😀ab'), new StringValue('b')))).toBe('2');
    expect(formatValue(call('string-find', new StringValue('😀ab'), new StringValue('z')))).toBe('nil');
  });
});

describe('qy.str string-replace', () => {
  test('empty pattern inserts between every code point (Python semantics)', () => {
    expect(text(call('string-replace', new StringValue('abc'), new StringValue(''), new StringValue('-')))).toBe(
      '-a-b-c-',
    );
    expect(text(call('string-replace', new StringValue(''), new StringValue(''), new StringValue('-')))).toBe('-');
    expect(text(call('string-replace', new StringValue('abc'), new StringValue(''), new StringValue('')))).toBe('abc');
  });

  test('optional arguments: split without a separator, slice with only start', () => {
    const parts = call('string-split', new StringValue('a b  c')) as TupleValue;
    expect(parts.items.map((item) => (item as StringValue).value)).toEqual(['a', 'b', 'c']);
    expect(text(call('string-slice', new StringValue('abc'), new IntValue(1n)))).toBe('bc');
  });

  test('empty separator raises the Python-compatible error', () => {
    expect(() => call('string-split', new StringValue('abc'), new StringValue(''))).toThrow('empty separator');
  });

  test('replaces all non-overlapping occurrences', () => {
    expect(text(call('string-replace', new StringValue('aaa'), new StringValue('a'), new StringValue('b')))).toBe(
      'bbb',
    );
    expect(text(call('string-replace', new StringValue('aaa'), new StringValue('aa'), new StringValue('b')))).toBe(
      'ba',
    );
  });
});
