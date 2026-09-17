// 字节码装载（JSON 契约）的单元测试。

import { describe, expect, test } from 'bun:test';
import { loadBytecodeJson } from '../src/bytecode.ts';
import { FloatValue, IntValue, QY_NIL, QY_T, Symbol, Chain, TupleValue } from '../src/values.ts';

function program(instructions: unknown[], registerCount = 4, extra: Record<string, unknown> = {}): string {
  return JSON.stringify({
    version: 1,
    main: 0,
    functions: [
      { name: '<main>', params: [], register_count: registerCount, instructions },
    ],
    ...extra,
  });
}

describe('loadBytecodeJson', () => {
  test('寄存器与标量操作数', () => {
    const text = program([
      { opcode: 'LOAD_HOST', operands: [{ type: 'reg', value: 0 }, { type: 't' }] },
      { opcode: 'RETURN', operands: [{ type: 'reg', value: 0 }] },
    ]);
    const parsed = loadBytecodeJson(text);
    expect(parsed.version).toBe(1);
    expect(parsed.functions[0].name).toBe('<main>');
    expect(parsed.functions[0].instructions[0].operands[0]).toBe(0);
    expect(parsed.functions[0].instructions[0].operands[1]).toBe(QY_T);
  });

  test('语义值 {type,class,value}', () => {
    const text = program([
      {
        opcode: 'LOAD_HOST',
        operands: [
          { type: 'reg', value: 0 },
          { type: 'int', class: 'IntValue', value: { value: { type: 'int', value: 6 } } },
        ],
      },
      {
        opcode: 'LOAD_HOST',
        operands: [
          { type: 'reg', value: 1 },
          { type: 'float', class: 'FloatValue', value: { value: { type: 'float', value: 1.5 } } },
        ],
      },
      { opcode: 'RETURN', operands: [{ type: 'reg', value: 0 }] },
    ]);
    const parsed = loadBytecodeJson(text);
    const first = parsed.functions[0].instructions[0].operands[1];
    const second = parsed.functions[0].instructions[1].operands[1];
    expect(first).toBeInstanceOf(IntValue);
    // 语义整型载荷按 BigInt 解码
    expect((first as IntValue).value).toBe(6n);
    expect(second).toBeInstanceOf(FloatValue);
    expect((second as FloatValue).value).toBe(1.5);
  });

  test('chain / nil / symbol / 元组操作数', () => {
    const text = program([
      {
        opcode: 'LOAD_HOST',
        operands: [
          { type: 'reg', value: 0 },
          {
            type: 'chain',
            value: {
              head: { type: 'symbol', value: '1' },
              tail: { head: { type: 'symbol', value: '2' }, tail: null },
            },
          },
        ],
      },
      {
        opcode: 'CALL_BUILTIN',
        operands: [
          { type: 'reg', value: 1 },
          { type: 'int', value: 0 },
          { type: 'tuple', value: [{ type: 'int', value: 0 }, { type: 'int', value: 0 }] },
        ],
      },
      { opcode: 'RETURN', operands: [{ type: 'reg', value: 0 }] },
    ]);
    const parsed = loadBytecodeJson(text);
    const chain = parsed.functions[0].instructions[0].operands[1];
    expect(chain).toBeInstanceOf(Chain);
    expect((chain as Chain).head).toBeInstanceOf(Symbol);
    expect((chain as Chain).tail).toBeInstanceOf(Chain);
    expect((chain as Chain).tail).toHaveProperty('tail', QY_NIL);
    const args = parsed.functions[0].instructions[1].operands[2];
    expect(args).toEqual([0, 0]);
  });

  test('handler_specs / import_specs / symbol_tuple', () => {
    const text = program([
      {
        opcode: 'HANDLE',
        operands: [
          { type: 'reg', value: 0 },
          { type: 'int', value: 1 },
          { type: 'handler_specs', value: [{ effect: 'ask', handler_fn: 2 }] },
        ],
      },
      {
        opcode: 'FROM_IMPORT',
        operands: [
          { type: 'symbol', value: 'qy.str' },
          { type: 'import_specs', value: [{ name: 'string-upper', alias: 'su' }] },
        ],
      },
      {
        opcode: 'DEFINE_MODULE',
        operands: [
          { type: 'int', value: 0 },
          { type: 'symbol', value: 'm' },
          { type: 'int', value: 1 },
          { type: 'symbol_tuple', value: ['pub'] },
        ],
      },
      { opcode: 'RETURN', operands: [{ type: 'reg', value: 0 }] },
    ]);
    const parsed = loadBytecodeJson(text);
    const [handle, fromImport, defineModule] = parsed.functions[0].instructions;
    const specs = handle.operands[2] as [Symbol, number][];
    expect(specs[0][0]).toBeInstanceOf(Symbol);
    expect(specs[0][0].name).toBe('ask');
    expect(specs[0][1]).toBe(2);
    expect((fromImport.operands[1] as { name: string }[])[0].alias).toBe('su');
    expect((defineModule.operands[3] as Symbol[])[0].name).toBe('pub');
  });

  test('hygiene_bindings 与版本校验', () => {
    const text = program([{ opcode: 'RETURN', operands: [{ type: 'reg', value: 0 }] }], 1, {
      hygiene_bindings: { __qy_hygiene_def___1: '+' },
    });
    const parsed = loadBytecodeJson(text);
    expect(parsed.hygieneBindings.get('__qy_hygiene_def___1')).toBe('+');
    expect(() => loadBytecodeJson(JSON.stringify({ version: 2, functions: [] }))).toThrow();
  });

  test('未知载荷报错（交换格式必须能编码所有常量）', () => {
    const text = program([
      { opcode: 'LOAD_HOST', operands: [{ type: 'reg', value: 0 }, { type: 'unknown', value: 'x' }] },
      { opcode: 'RETURN', operands: [{ type: 'reg', value: 0 }] },
    ]);
    expect(() => loadBytecodeJson(text)).toThrow();
  });

  test('TupleValue 语义值', () => {
    const text = program([
      {
        opcode: 'LOAD_HOST',
        operands: [
          { type: 'reg', value: 0 },
          {
            type: 'tuple',
            class: 'TupleValue',
            value: { items: { type: 'tuple', value: [{ type: 'int', class: 'IntValue', value: { value: { type: 'int', value: 1 } } }] } },
          },
        ],
      },
      { opcode: 'RETURN', operands: [{ type: 'reg', value: 0 }] },
    ]);
    const parsed = loadBytecodeJson(text);
    const value = parsed.functions[0].instructions[0].operands[1];
    expect(value).toBeInstanceOf(TupleValue);
    expect((value as TupleValue).items[0]).toBeInstanceOf(IntValue);
  });
});
