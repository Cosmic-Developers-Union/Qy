#!/usr/bin/env bun
// 示例 2：宿主语言扩展 —— 用 TypeScript 写算子，注册进 Qy 虚拟机。
//
//   bun examples/ts/host_functions.ts
//
// 演示三件事：
//   1. `registerHostFunction(name, fn)`：把 TS 函数注册成 Qy 纯算子（参数与返回值都是
//      Qy 语义值，用 `values` 里的构造器包装）；
//   2. 宿主注册**同名算子会覆盖**标准 profile 的实现（这里覆盖 `print`），说明宿主
//      扩展在运行时对语言可见；同时演示宿主接管 Qy 的输出（`setOutputWriter`）；
//   3. `define(name, value)`：宿主向 Qy 环境注入常量。
//
// 重要约束：编译器在**编译期**解析符号，所以程序里出现的名字必须在编译期可解析
// （标准 profile 或 `from` 导入）。因此本示例覆盖 `display` 而不是引入全新名字；
// 若要引入全新算子，需要让编译期环境也知道该名字（例如 Python 侧先注册占位再导出）。
//
// 注意：`print` 在标准 profile 里是 effect 算子（参数策略 raw），而 registerHostFunction
// 注册的是纯算子（参数已求值）；示例覆盖它只为演示「同名覆盖」这一机制。

import {
  createVm,
  formatValue,
  setOutputWriter,
  values,
} from '../../qy/backend/typescript/src/embed.ts';
import { compileWithQy, expectEqual } from './support.ts';

const program = 'examples/qy/host_print.qy';
const bytecode = await Bun.file(await compileWithQy(program)).text();

/** 运行程序，返回（被 Qy 写到 stdout 的文本, runLines 的结果行）。 */
async function runCapturingOutput(
  register?: (vm: ReturnType<typeof createVm>) => void,
): Promise<{ output: string; lines: string[] }> {
  const chunks: string[] = [];
  setOutputWriter((text) => chunks.push(text));
  try {
    const vm = createVm(bytecode);
    register?.(vm);
    const lines = await vm.runLines();
    return { output: chunks.join(''), lines };
  } finally {
    setOutputWriter((text) => process.stdout.write(text));
  }
}

// 1) 标准 profile 的 print
const plain = await runCapturingOutput();
if (!plain.output.startsWith('42')) {
  throw new Error(`标准 print 输出异常: ${JSON.stringify(plain.output)}`);
}

// 2) 宿主覆盖 print：TS 实现
const seen: string[] = [];
const hosted = await runCapturingOutput((vm) => {
  vm.registerHostFunction('print', (value) => {
    seen.push(formatValue(value));
    return new values.StringValue('host-print');
  });
});

if (seen.length !== 1) {
  throw new Error(`宿主 print 应被调用 1 次，实际 ${seen.length} 次`);
}
expectEqual(seen[0] ?? '', '42', '宿主 print 收到的值');
expectEqual(hosted.output, '', '宿主 print 返回 Qy 值，不再直接写 stdout');
expectEqual(hosted.lines.join(' | '), 'host-print', '宿主 print 的返回值成为结果行');

// 3) 注册新算子 + 注入常量（宿主侧可直接使用；编译期未解析的名字不写进程序）
const vm = createVm(bytecode);
vm.registerHostFunction('host-double', (value) => {
  if (!(value instanceof values.IntValue)) {
    throw new Error('host-double expects an int');
  }
  return new values.IntValue(value.value * 2);
});
vm.define('host-answer', new values.IntValue(42));

const doubled = vm.env.resolve(new values.Symbol('host-double'));
const answer = vm.env.resolve(new values.Symbol('host-answer'));
expectEqual(formatValue(answer), '42', '宿主注入的常量');

console.log('标准 print 输出:', JSON.stringify(plain.output));
console.log('宿主 print 调用:', seen.join(' | '));
console.log('宿主注入常量 host-answer =', formatValue(answer));
console.log('宿主算子 host-double 已注册:', doubled instanceof values.PureOperatorValue ? 'yes' : 'no');
