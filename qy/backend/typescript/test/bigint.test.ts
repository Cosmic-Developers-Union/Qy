// 大整数（BigInt 语义）单元测试。
//
// 对应 Python：
//   - `qy/sem/core.py::IntValue`（任意精度 int）
//   - `qy/session/number_ops.py`（定宽范围检查、同 concrete 类型约束）
//   - `qy/backend/vm/bytecode.py`（交换格式里 int 常量的精确编解码）

import { describe, expect, test } from 'bun:test';

import {
  FloatValue,
  Int32Value,
  IntValue,
  Symbol,
  UInt8Value,
  integerPayload,
  numberPayloadEquals,
} from '../src/values.ts';
import { parseIntLiteral, tryDefaultLiteral } from '../src/environment.ts';
import { add, div, le, lt, mod, mul, numEq, sub } from '../src/stdlib/arithmetic.ts';
import { formatValue } from '../src/display.ts';
import { loadBytecodeJson } from '../src/bytecode.ts';
import { QyEffectSignal } from '../src/errors.ts';

/** 触发 effect 时返回信号；没有触发返回 null。 */
function effectOf(run: () => unknown): QyEffectSignal | null {
  try {
    run();
    return null;
  } catch (error) {
    if (error instanceof QyEffectSignal) return error;
    throw error;
  }
}

describe('大整数字面量', () => {
  test('parseIntLiteral 保留任意精度', () => {
    expect(parseIntLiteral('9007199254740993')).toBe(9007199254740993n);
    expect(parseIntLiteral('-9007199254740993')).toBe(-9007199254740993n);
    expect(parseIntLiteral('100000000000000000000000000007')).toBe(100000000000000000000000000007n);
    // 下划线分组与 Python int() 一致
    expect(parseIntLiteral('1_000_000')).toBe(1000000n);
  });

  test('tryDefaultLiteral 构造 BigInt IntValue', () => {
    const value = tryDefaultLiteral(new Symbol('9007199254740993'));
    expect(value).toBeInstanceOf(IntValue);
    expect(integerPayload(value as IntValue)).toBe(9007199254740993n);
  });

  test('formatValue 输出十进制，不出现宿主 `123n`', () => {
    expect(formatValue(new IntValue(9007199254740993n))).toBe('9007199254740993');
    expect(formatValue(new IntValue(-42n))).toBe('-42');
  });
});

describe('大整数算术', () => {
  test('加减乘精确', () => {
    // (+ 9007199254740993 1)
    expect(formatValue(add(new IntValue(9007199254740993n), new IntValue(1n)))).toBe(
      '9007199254740994',
    );
    // (* 9007199254740993 9007199254740993)
    expect(formatValue(mul(new IntValue(9007199254740993n), new IntValue(9007199254740993n)))).toBe(
      '81129638414606699710187514626049',
    );
    expect(formatValue(sub(new IntValue(0n), new IntValue(9007199254740993n)))).toBe(
      '-9007199254740993',
    );
  });

  test('比较与相等', () => {
    expect(formatValue(lt(new IntValue(100000000000000000000n), new IntValue(100000000000000000001n)))).toBe('T');
    expect(
      formatValue(le(new IntValue(9007199254740993n), new IntValue(9007199254740993n))),
    ).toBe('T');
    expect(formatValue(numEq(new IntValue(9007199254740993n), new IntValue(9007199254740993n)))).toBe('T');
  });

  test('取模（符号跟随除数）与向零截断除法', () => {
    expect(formatValue(mod(new IntValue(100000000000000000000000000007n), new IntValue(97n)))).toBe('64');
    expect(formatValue(mod(new IntValue(-7n), new IntValue(3n)))).toBe('2');
    expect(formatValue(mod(new IntValue(7n), new IntValue(-3n)))).toBe('-2');
    expect(formatValue(div(new IntValue(7n), new IntValue(2n)))).toBe('3');
    expect(formatValue(div(new IntValue(-7n), new IntValue(2n)))).toBe('-3');
    // 单参数 `/` 在 Python `_integer_div` 里用 `1 // first`（floor），不是截断
    expect(formatValue(div(new IntValue(-2n)))).toBe('-1');
    // 异号且余数非零时 Python 走 `int(result / divisor)`（float 除法），
    // 超大字面量会丢精度；这里逐字复刻，保证与 Python 逐字节一致。
    expect(formatValue(div(new IntValue(-100000000000000000000n), new IntValue(7n)))).toBe(
      '-14285714285714286592',
    );
  });

  test('numberPayloadEquals 跨 bigint / number', () => {
    expect(numberPayloadEquals(1n, 1)).toBe(true);
    expect(numberPayloadEquals(1n, 2)).toBe(false);
    expect(numberPayloadEquals(9007199254740993n, 9007199254740993n)).toBe(true);
  });
});

describe('定宽整型溢出与混合类型', () => {
  test('int32 溢出触发 numeric-overflow', () => {
    const signal = effectOf(() => add(new Int32Value(2147483647n), new Int32Value(1n)));
    expect(signal).not.toBeNull();
    expect(signal?.effect).toBe('numeric-overflow');
  });

  test('uint8 负数下溢触发 numeric-overflow', () => {
    const signal = effectOf(() => sub(new UInt8Value(0n), new UInt8Value(1n)));
    expect(signal?.effect).toBe('numeric-overflow');
  });

  test('大整数与浮点混合触发 unsupported-operation', () => {
    const signal = effectOf(() => add(new IntValue(9007199254740993n), new FloatValue(1.5)));
    expect(signal).not.toBeNull();
    expect(signal?.effect).toBe('unsupported-operation');
  });
});

describe('交换格式的大整数', () => {
  test('loadBytecodeJson 精确保留超出 2^53 的 int 常量', () => {
    // 注意：这里必须用原始 JSON 文本，`JSON.stringify` 会在写侧就把精度丢掉。
    const text =
      '{"version":1,"main":0,"functions":[{"name":"<main>","params":[],"register_count":1,' +
      '"instructions":[{"opcode":"LOAD_HOST","operands":[{"type":"reg","value":0},' +
      '{"type":"int","class":"IntValue","value":{"value":{"type":"int","value":9007199254740993}}}]},' +
      '{"opcode":"RETURN","operands":[{"type":"reg","value":0}]}]}]}';
    const parsed = loadBytecodeJson(text);
    const value = parsed.functions[0].instructions[0].operands[1];
    expect(value).toBeInstanceOf(IntValue);
    expect(integerPayload(value as IntValue)).toBe(9007199254740993n);
    expect(formatValue(value)).toBe('9007199254740993');
  });
});
