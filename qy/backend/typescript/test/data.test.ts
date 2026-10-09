// `qy.core` 数据算子的 arity 与类型诊断。
//
// 运行：bun test（在 qy/backend/typescript 下）

import { describe, expect, test } from 'bun:test';
import { dataBindings } from '../src/stdlib/data.ts';
import { IntValue } from '../src/values.ts';

const ops = dataBindings();
const call = (name: string, ...args: unknown[]): unknown =>
  (ops[name] as (...a: unknown[]) => unknown)(...args);

describe('qy.core data arity', () => {
  test('get requires two or three arguments', () => {
    expect(() => call('get', new IntValue(0n))).toThrow('get expects two or three arguments, got 1');
  });

  test('has? requires exactly two arguments', () => {
    expect(() => call('has?', new IntValue(0n))).toThrow('has? expects exactly two arguments, got 1');
  });
});
