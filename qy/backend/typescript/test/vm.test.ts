// VM 指令语义的单元测试。
//
// 这些程序用与 `qy export` 相同的 JSON 形状手写，覆盖：
// 算术 / 比较、控制流、闭包与递归、代数效应（perform/handle/resume）、
// 模块与 import、宿主函数、RUNTIME_EVAL、以及 APPLY 的字面量归一。

import { describe, expect, test } from 'bun:test';
import { createVm, evalBytecode, getOutputWriter, setOutputWriter } from '../src/embed.ts';
import { formatValue } from '../src/display.ts';
import {
  Chain,
  IntValue,
  QY_NIL,
  QY_T,
  StringValue,
  Symbol,
  TupleValue,
  listToChain,
  type QyValue,
} from '../src/values.ts';
import { add, numEq, sub } from '../src/stdlib/arithmetic.ts';
import { callBuiltin } from '../src/stdlib/index.ts';
import { QyEffectSignal } from '../src/errors.ts';

// -- 手写字节码的小工具 ------------------------------------------------------

const R = (index: number) => ({ type: 'reg', value: index });
const I = (value: number) => ({ type: 'int', value });
const S = (name: string) => ({ type: 'symbol', value: name });
const IV = (value: number) => ({ type: 'int', class: 'IntValue', value: { value: { type: 'int', value } } });
const FV = (value: number) => ({ type: 'float', class: 'FloatValue', value: { value: { type: 'float', value } } });
const T = { type: 't' };
const NIL = { type: 'nil' };

interface FnSpec {
  name: string;
  params?: string[];
  register_count: number;
  instructions: { opcode: string; operands: unknown[] }[];
}

function program(functions: FnSpec[], extra: Record<string, unknown> = {}): string {
  return JSON.stringify({
    version: 1,
    main: 0,
    functions: functions.map((fn) => ({
      name: fn.name,
      params: fn.params ?? [],
      register_count: fn.register_count,
      instructions: fn.instructions,
    })),
    ...extra,
  });
}

async function run(source: string): Promise<QyValue[]> {
  return await evalBytecode(source);
}

// -- 单元 --------------------------------------------------------------------

describe('stdlib 基本算子', () => {
  test('CALL_BUILTIN ABI 下标', () => {
    expect(formatValue(callBuiltin(0, [new IntValue(2), new IntValue(3)]))).toBe('5');
    expect(formatValue(callBuiltin(1, [new IntValue(10), new IntValue(3)]))).toBe('7');
    expect(formatValue(callBuiltin(2, [new IntValue(4), new IntValue(5)]))).toBe('20');
    expect(formatValue(callBuiltin(3, [new IntValue(20), new IntValue(5)]))).toBe('4');
    expect(formatValue(callBuiltin(4, [new IntValue(1), new IntValue(1)]))).toBe('T');
    expect(formatValue(callBuiltin(5, [new IntValue(1), new IntValue(2)]))).toBe('nil');
    expect(formatValue(callBuiltin(13, [new IntValue(1), QY_NIL]))).toBe('(1)');
    expect(formatValue(callBuiltin(14, [listToChain([new IntValue(1)])]))).toBe('1');
    expect(formatValue(callBuiltin(15, [listToChain([new IntValue(1), new IntValue(2)])]))).toBe('(2)');
  });

  test('整数除法向零截断', () => {
    expect(formatValue(callBuiltin(3, [new IntValue(-7), new IntValue(2)]))).toBe('-3');
    expect(formatValue(callBuiltin(3, [new IntValue(7), new IntValue(2)]))).toBe('3');
  });

  test('混合 concrete number 类型不隐式提升', () => {
    const mixed = program([
      {
        name: '<main>',
        register_count: 3,
        instructions: [
          { opcode: 'LOAD_HOST', operands: [R(0), IV(1)] },
          { opcode: 'LOAD_HOST', operands: [R(1), FV(1)] },
          { opcode: 'CALL_BUILTIN', operands: [R(2), I(0), { type: 'tuple', value: [I(0), I(1)] }] },
          { opcode: 'RETURN', operands: [R(2)] },
        ],
      },
    ]);
    expect(run(mixed)).rejects.toBeInstanceOf(QyEffectSignal);
  });

  test('除零触发 divide-by-zero', () => {
    expect(() => callBuiltin(3, [new IntValue(1), new IntValue(0)])).toThrow(QyEffectSignal);
  });

  test('数值比较与 `=`', () => {
    expect(formatValue(numEq(new IntValue(1), new IntValue(1)))).toBe('T');
    expect(formatValue(numEq(new IntValue(1), new StringValue('1')))).toBe('nil');
    expect(formatValue(add(new IntValue(1), new IntValue(2), new IntValue(3)))).toBe('6');
    expect(formatValue(sub(new IntValue(7)))).toBe('-7');
  });

  test('`=` 对 symbol 用 identity，`eq` 用结构', () => {
    const left = new Symbol('yes');
    const right = new Symbol('yes');
    expect(formatValue(numEq(left, right))).toBe('nil');
    expect(formatValue(numEq(QY_NIL, QY_NIL))).toBe('T');
    expect(formatValue(callBuiltin(5, [left, right]))).toBe('T');
  });
});

describe('VM 指令', () => {
  test('算术 + APPEND_RESULT', async () => {
    const source = program([
      {
        name: '<main>',
        register_count: 4,
        instructions: [
          { opcode: 'LOAD_HOST', operands: [R(0), IV(1)] },
          { opcode: 'LOAD_HOST', operands: [R(1), IV(2)] },
          { opcode: 'CALL_BUILTIN', operands: [R(2), I(0), { type: 'tuple', value: [I(0), I(1)] }] },
          { opcode: 'APPEND_RESULT', operands: [R(2)] },
          { opcode: 'RETURN', operands: [R(2)] },
        ],
      },
    ]);
    expect((await run(source)).map(formatValue)).toEqual(['3']);
  });

  test('JUMP_IF_FALSE 只用 nil 判定真假', async () => {
    // (= (cond-like) ...)：0 为真，因此走 then 分支
    const source = program([
      {
        name: '<main>',
        register_count: 3,
        instructions: [
          { opcode: 'LOAD_HOST', operands: [R(0), IV(0)] },
          { opcode: 'JUMP_IF_FALSE', operands: [R(0), I(4)] },
          { opcode: 'LOAD_HOST', operands: [R(1), IV(1)] },
          { opcode: 'JUMP', operands: [I(6)] },
          { opcode: 'LOAD_HOST', operands: [R(1), IV(2)] },
          { opcode: 'JUMP', operands: [I(6)] },
          { opcode: 'APPEND_RESULT', operands: [R(1)] },
          { opcode: 'RETURN', operands: [R(1)] },
        ],
      },
    ]);
    expect((await run(source)).map(formatValue)).toEqual(['1']);
  });

  test('闭包、递归与 TAIL_CALL', async () => {
    const source = program([
      {
        name: '<main>',
        register_count: 4,
        instructions: [
          { opcode: 'MAKE_FUNCTION', operands: [R(0), I(1)] },
          { opcode: 'DEFINE_ONCE', operands: [S('fact'), R(0)] },
          { opcode: 'LOAD_ENV', operands: [R(1), S('fact')] },
          { opcode: 'LOAD_HOST', operands: [R(2), IV(5)] },
          { opcode: 'CALL', operands: [R(3), R(1), { type: 'reg_tuple', value: [2] }] },
          { opcode: 'APPEND_RESULT', operands: [R(3)] },
          { opcode: 'RETURN', operands: [R(3)] },
        ],
      },
      {
        name: 'fact',
        params: ['n'],
        register_count: 8,
        instructions: [
          { opcode: 'LOAD_ENV', operands: [R(0), S('=')] },
          { opcode: 'LOAD_ENV', operands: [R(1), S('n')] },
          { opcode: 'LOAD_HOST', operands: [R(2), IV(0)] },
          { opcode: 'CALL_BUILTIN', operands: [R(3), I(4), { type: 'tuple', value: [I(1), I(2)] }] },
          { opcode: 'JUMP_IF_FALSE', operands: [R(3), I(7)] },
          { opcode: 'LOAD_HOST', operands: [R(1), IV(1)] },
          { opcode: 'RETURN', operands: [R(1)] },
          { opcode: 'LOAD_ENV', operands: [R(1), S('*')] },
          { opcode: 'LOAD_ENV', operands: [R(2), S('n')] },
          { opcode: 'LOAD_ENV', operands: [R(3), S('fact')] },
          { opcode: 'LOAD_ENV', operands: [R(4), S('-')] },
          { opcode: 'LOAD_ENV', operands: [R(5), S('n')] },
          { opcode: 'LOAD_HOST', operands: [R(6), IV(1)] },
          { opcode: 'CALL_BUILTIN', operands: [R(7), I(1), { type: 'tuple', value: [I(5), I(6)] }] },
          { opcode: 'CALL', operands: [R(4), R(3), { type: 'reg_tuple', value: [7] }] },
          { opcode: 'TAIL_CALL', operands: [R(1), { type: 'reg_tuple', value: [2, 4] }] },
        ],
      },
    ]);
    expect((await run(source)).map(formatValue)).toEqual(['120']);
  });

  test('代数效应：perform / handle / resume', async () => {
    const source = program([
      {
        name: '<main>',
        register_count: 4,
        instructions: [
          { opcode: 'DEFEFFECT', operands: [S('ask'), true] },
          {
            opcode: 'HANDLE',
            operands: [R(0), I(1), { type: 'handler_specs', value: [{ effect: 'ask', handler_fn: 2 }] }],
          },
          { opcode: 'APPEND_RESULT', operands: [R(0)] },
          { opcode: 'RETURN', operands: [R(0)] },
        ],
      },
      {
        name: '<handle-body>',
        register_count: 1,
        instructions: [
          { opcode: 'LOAD_HOST', operands: [R(0), IV(7)] },
          { opcode: 'PERFORM', operands: [R(0), S('ask'), R(0)] },
          { opcode: 'RETURN', operands: [R(0)] },
        ],
      },
      {
        name: '<handler-ask>',
        params: ['x', 'k'],
        register_count: 5,
        instructions: [
          { opcode: 'LOAD_ENV', operands: [R(0), S('k')] },
          { opcode: 'LOAD_ENV', operands: [R(1), S('+')] },
          { opcode: 'LOAD_ENV', operands: [R(2), S('x')] },
          { opcode: 'LOAD_HOST', operands: [R(3), IV(35)] },
          { opcode: 'CALL_BUILTIN', operands: [R(4), I(0), { type: 'tuple', value: [I(2), I(3)] }] },
          { opcode: 'RESUME', operands: [R(2), R(0), R(4)] },
          { opcode: 'RETURN', operands: [R(2)] },
        ],
      },
    ]);
    expect((await run(source)).map(formatValue)).toEqual(['42']);
  });

  test('模块定义与 from import', async () => {
    const source = program([
      {
        name: '<main>',
        register_count: 4,
        instructions: [
          { opcode: 'DEFINE_MODULE', operands: [I(0), S('m'), I(1), { type: 'symbol_tuple', value: ['pub'] }] },
          {
            opcode: 'FROM_IMPORT',
            operands: [S('m'), { type: 'import_specs', value: [{ name: 'pub', alias: 'pub' }] }],
          },
          { opcode: 'LOAD_ENV', operands: [R(1), S('pub')] },
          { opcode: 'CALL', operands: [R(2), R(1), { type: 'reg_tuple', value: [] }] },
          { opcode: 'APPEND_RESULT', operands: [R(2)] },
          { opcode: 'RETURN', operands: [R(2)] },
        ],
      },
      {
        name: '<module-body>',
        register_count: 1,
        instructions: [
          { opcode: 'MAKE_FUNCTION', operands: [R(0), I(2)] },
          { opcode: 'DEFINE_ONCE', operands: [S('pub'), R(0)] },
          { opcode: 'RETURN', operands: [R(0)] },
        ],
      },
      {
        name: 'pub',
        register_count: 1,
        instructions: [
          { opcode: 'LOAD_HOST', operands: [R(0), IV(2)] },
          { opcode: 'RETURN', operands: [R(0)] },
        ],
      },
    ]);
    expect((await run(source)).map(formatValue)).toEqual(['2']);
  });

  test('APPLY 把字面量拼写还原为值', async () => {
    const quoteChain = {
      type: 'chain',
      value: {
        head: { type: 'symbol', value: '1' },
        tail: {
          head: { type: 'symbol', value: '2' },
          tail: { head: { type: 'symbol', value: '3' }, tail: null },
        },
      },
    };
    const source = program([
      {
        name: '<main>',
        register_count: 4,
        instructions: [
          { opcode: 'LOAD_ENV', operands: [R(0), S('+')] },
          { opcode: 'LOAD_HOST', operands: [R(1), quoteChain] },
          { opcode: 'APPLY', operands: [R(2), R(0), R(1)] },
          { opcode: 'APPEND_RESULT', operands: [R(2)] },
          { opcode: 'RETURN', operands: [R(2)] },
        ],
      },
    ]);
    expect((await run(source)).map(formatValue)).toEqual(['6']);
  });

  test('RUNTIME_EVAL 解析符号（reify 往返）', async () => {
    const source = program([
      {
        name: '<main>',
        register_count: 3,
        instructions: [
          { opcode: 'LOAD_HOST', operands: [R(0), S('42')] },
          { opcode: 'RUNTIME_EVAL', operands: [R(1), R(0)] },
          { opcode: 'APPEND_RESULT', operands: [R(1)] },
          { opcode: 'RETURN', operands: [R(1)] },
        ],
      },
    ]);
    const results = await run(source);
    expect(results[0]).toBeInstanceOf(IntValue);
    expect(formatValue(results[0])).toBe('42');
  });

  test('reify 产生 symbol 拼写', async () => {
    const source = program([
      {
        name: '<main>',
        register_count: 3,
        instructions: [
          { opcode: 'LOAD_ENV', operands: [R(0), S('reify')] },
          { opcode: 'LOAD_HOST', operands: [R(1), IV(42)] },
          { opcode: 'CALL', operands: [R(2), R(0), { type: 'reg_tuple', value: [1] }] },
          { opcode: 'APPEND_RESULT', operands: [R(2)] },
          { opcode: 'RETURN', operands: [R(2)] },
        ],
      },
    ]);
    const results = await run(source);
    expect(results[0]).toBeInstanceOf(Symbol);
    expect((results[0] as Symbol).name).toBe('42');
  });

  test('module 环境隔离：模块内 define 不泄漏到外层', async () => {
    const source = program([
      {
        name: '<main>',
        register_count: 2,
        instructions: [
          { opcode: 'DEFINE_MODULE', operands: [I(0), S('m'), I(1), { type: 'symbol_tuple', value: [] }] },
          { opcode: 'LOAD_HOST', operands: [R(1), NIL] },
          { opcode: 'APPEND_RESULT', operands: [R(1)] },
          { opcode: 'RETURN', operands: [R(1)] },
        ],
      },
      {
        name: '<module-body>',
        register_count: 1,
        instructions: [
          { opcode: 'LOAD_HOST', operands: [R(0), IV(1)] },
          { opcode: 'DEFINE_ONCE', operands: [S('hidden'), R(0)] },
          { opcode: 'RETURN', operands: [R(0)] },
        ],
      },
    ]);
    const vm = createVm(source);
    await vm.run();
    expect(() => vm.env.resolve(new Symbol('hidden'))).toThrow();
  });
});

describe('嵌入式 API', () => {
  test('registerHostFunction', async () => {
    const source = program([
      {
        name: '<main>',
        register_count: 3,
        instructions: [
          { opcode: 'LOAD_ENV', operands: [R(0), S('triple')] },
          { opcode: 'LOAD_HOST', operands: [R(1), IV(4)] },
          { opcode: 'CALL', operands: [R(2), R(0), { type: 'reg_tuple', value: [1] }] },
          { opcode: 'APPEND_RESULT', operands: [R(2)] },
          { opcode: 'RETURN', operands: [R(2)] },
        ],
      },
    ]);
    const vm = createVm(source);
    vm.registerHostFunction('triple', (value: QyValue) => new IntValue((value as IntValue).value * 3n));
    const results = await vm.run();
    expect(formatValue(results[0])).toBe('12');
    expect(await vm.runLines()).toEqual(['12']);
  });

  test('hygiene_bindings 参与 LOAD_ENV 解析', async () => {
    const source = program(
      [
        {
          name: '<main>',
          register_count: 4,
          instructions: [
            { opcode: 'LOAD_ENV', operands: [R(0), { type: 'symbol', value: '__qy_hygiene_def___1' }] },
            { opcode: 'LOAD_HOST', operands: [R(1), IV(3)] },
            { opcode: 'LOAD_HOST', operands: [R(2), IV(4)] },
            { opcode: 'CALL', operands: [R(3), R(0), { type: 'reg_tuple', value: [1, 2] }] },
            { opcode: 'APPEND_RESULT', operands: [R(3)] },
            { opcode: 'RETURN', operands: [R(3)] },
          ],
        },
      ],
      { hygiene_bindings: { __qy_hygiene_def___1: '+' } },
    );
    expect((await run(source)).map(formatValue)).toEqual(['7']);
  });

  test('结果过滤规则（绑定形式产物不打印）', async () => {
    const source = program([
      {
        name: '<main>',
        register_count: 3,
        instructions: [
          { opcode: 'MAKE_FUNCTION', operands: [R(0), I(1)] },
          { opcode: 'DEFINE_ONCE', operands: [S('f'), R(0)] },
          { opcode: 'APPEND_RESULT', operands: [R(0)] },
          { opcode: 'DEFEFFECT', operands: [S('e'), true] },
          { opcode: 'LOAD_ENV', operands: [R(1), S('e')] },
          { opcode: 'APPEND_RESULT', operands: [R(1)] },
          { opcode: 'LOAD_HOST', operands: [R(2), T] },
          { opcode: 'APPEND_RESULT', operands: [R(2)] },
          { opcode: 'RETURN', operands: [R(2)] },
        ],
      },
      {
        name: 'f',
        register_count: 1,
        instructions: [
          { opcode: 'LOAD_HOST', operands: [R(0), NIL] },
          { opcode: 'RETURN', operands: [R(0)] },
        ],
      },
    ]);
    const vm = createVm(source);
    expect(await vm.runLines()).toEqual(['T']);
  });

  test('TupleValue 与 Chain 值可以互转（用于宿主）', () => {
    const tuple = new TupleValue([new IntValue(1)]);
    const chain = listToChain(tuple.items);
    expect(chain).toBeInstanceOf(Chain);
    expect(formatValue(chain)).toBe('(1)');
  });

  test('parallel/all 真并发：async 宿主函数在同一批次内重叠执行', async () => {
    // 两个 thunk 都调用 async 宿主函数 delay(ms, value)。
    const source = program([
      {
        name: '<main>',
        register_count: 4,
        instructions: [
          // PARALLEL_GATHER 的操作数是 thunk 的**函数下标**（1、2）
          { opcode: 'PARALLEL_GATHER', operands: [R(3), R(1), R(2)] },
          { opcode: 'APPEND_RESULT', operands: [R(3)] },
          { opcode: 'RETURN', operands: [R(3)] },
        ],
      },
      {
        name: '<parallel-thunk-slow>',
        register_count: 3,
        instructions: [
          { opcode: 'LOAD_ENV', operands: [R(0), S('delay')] },
          { opcode: 'LOAD_HOST', operands: [R(1), IV(20)] },
          { opcode: 'LOAD_HOST', operands: [R(2), IV(1)] },
          { opcode: 'TAIL_CALL', operands: [R(0), { type: 'reg_tuple', value: [1, 2] }] },
        ],
      },
      {
        name: '<parallel-thunk-fast>',
        register_count: 3,
        instructions: [
          { opcode: 'LOAD_ENV', operands: [R(0), S('delay')] },
          { opcode: 'LOAD_HOST', operands: [R(1), IV(5)] },
          { opcode: 'LOAD_HOST', operands: [R(2), IV(2)] },
          { opcode: 'TAIL_CALL', operands: [R(0), { type: 'reg_tuple', value: [1, 2] }] },
        ],
      },
    ]);
    const events: string[] = [];
    const vm = createVm(source);
    vm.registerHostFunction('delay', async (ms, value) => {
      events.push(`start:${formatValue(value)}`);
      await new Promise((resolve) => setTimeout(resolve, Number((ms as IntValue).value)));
      events.push(`end:${formatValue(value)}`);
      return value;
    });
    const results = await vm.run();
    // 结果顺序与 thunk 声明顺序一致（Promise.allSettled 保序，等价 asyncio.gather）
    expect(formatValue(results[0])).toBe('(1 2)');
    // 真并发的证据：第 2 个 thunk 在第一个结束之前已经开始
    expect(events).toContain('start:1');
    expect(events).toContain('start:2');
    expect(events.indexOf('start:2')).toBeLessThan(events.indexOf('end:1'));
  });

  test('race 真并发：最快的 async thunk 胜出', async () => {
    const source = program([
      {
        name: '<main>',
        register_count: 1,
        instructions: [
          { opcode: 'RACE_FIRST', operands: [R(0), R(1), R(2)] },
          { opcode: 'APPEND_RESULT', operands: [R(0)] },
          { opcode: 'RETURN', operands: [R(0)] },
        ],
      },
      {
        name: '<race-thunk-slow>',
        register_count: 3,
        instructions: [
          { opcode: 'LOAD_ENV', operands: [R(0), S('delay')] },
          { opcode: 'LOAD_HOST', operands: [R(1), IV(20)] },
          { opcode: 'LOAD_HOST', operands: [R(2), IV(1)] },
          { opcode: 'TAIL_CALL', operands: [R(0), { type: 'reg_tuple', value: [1, 2] }] },
        ],
      },
      {
        name: '<race-thunk-fast>',
        register_count: 3,
        instructions: [
          { opcode: 'LOAD_ENV', operands: [R(0), S('delay')] },
          { opcode: 'LOAD_HOST', operands: [R(1), IV(5)] },
          { opcode: 'LOAD_HOST', operands: [R(2), IV(2)] },
          { opcode: 'TAIL_CALL', operands: [R(0), { type: 'reg_tuple', value: [1, 2] }] },
        ],
      },
    ]);
    const vm = createVm(source);
    vm.registerHostFunction('delay', async (ms, value) => {
      await new Promise((resolve) => setTimeout(resolve, Number((ms as IntValue).value)));
      return value;
    });
    const results = await vm.run();
    expect(formatValue(results[0])).toBe('2');
  });

  test('有 IO 的分支保持顺序执行（并发边界）', async () => {
    // thunk 里 LOAD_ENV 'print' 命中副作用名单 → 整批退回顺序执行，
    // 输出顺序必须是 thunk 声明顺序，而不是并发交错的顺序。
    const source = program([
      {
        name: '<main>',
        register_count: 1,
        instructions: [
          { opcode: 'ALL_GATHER', operands: [R(0), R(1), R(2)] },
          { opcode: 'APPEND_RESULT', operands: [R(0)] },
          { opcode: 'RETURN', operands: [R(0)] },
        ],
      },
      {
        name: '<io-thunk-a>',
        register_count: 2,
        instructions: [
          { opcode: 'LOAD_ENV', operands: [R(0), S('print')] },
          { opcode: 'LOAD_HOST', operands: [R(1), { type: 'string', class: 'StringValue', value: { value: { type: 'string', value: 'a' } } }] },
          { opcode: 'TAIL_CALL', operands: [R(0), { type: 'reg_tuple', value: [1] }] },
        ],
      },
      {
        name: '<io-thunk-b>',
        register_count: 2,
        instructions: [
          { opcode: 'LOAD_ENV', operands: [R(0), S('print')] },
          { opcode: 'LOAD_HOST', operands: [R(1), { type: 'string', class: 'StringValue', value: { value: { type: 'string', value: 'b' } } }] },
          { opcode: 'TAIL_CALL', operands: [R(0), { type: 'reg_tuple', value: [1] }] },
        ],
      },
    ]);
    const captured: string[] = [];
    const original = getOutputWriter();
    setOutputWriter((text) => captured.push(text));
    try {
      const vm = createVm(source);
      await vm.run();
    } finally {
      setOutputWriter(original);
    }
    expect(captured.join('')).toBe('a\nb\n');
  });
});
