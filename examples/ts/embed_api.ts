#!/usr/bin/env bun
// 示例 3：嵌入式 API 用法（createVm / evalBytecode / 原始值与文本行 / 错误处理）。
//
//   bun examples/ts/embed_api.ts
//
// 面向"把 Qy 当作库来用"的场景：宿主拿到字节码后，可以
//   - 用 `evalBytecode()` 一次性求值拿原始 Qy 值；
//   - 用 `createVm()` 建可复用句柄，多次运行、注入宿主函数/常量；
//   - 用 `formatValue()` 自行决定如何呈现结果。

import { evalBytecode, createVm, formatValue, loadBytecodeJson } from '../../qy/backend/typescript/src/embed.ts';
import type { QyValue } from '../../qy/backend/typescript/src/values.ts';
import { compileWithQy, defaultProgram, expectEqual } from './support.ts';

const bytecode = await Bun.file(await compileWithQy(defaultProgram)).text();

// 1) 一次性求值：返回全部顶层结果（含绑定形式产物，未过滤）
const raw: QyValue[] = await evalBytecode(bytecode);
const text = raw.map((value) => formatValue(value)).join(' | ');
expectEqual(text, '42', 'evalBytecode 原始结果');
console.log('evalBytecode ->', text);

// 2) 可复用句柄：同一个程序跑两次（每次都有独立环境状态）
const vm = createVm(loadBytecodeJson(bytecode));
expectEqual((await vm.runLines()).join(' | '), '42', '第 1 次运行');
expectEqual((await vm.runLines()).join(' | '), '42', '第 2 次运行');
console.log('可复用句柄两次运行结果一致');

// 3) 错误处理：非法字节码 JSON 必须抛出可捕获的错误，而不是静默失败
let caught = '';
try {
  createVm('{ not json }');
} catch (error) {
  caught = error instanceof Error ? error.message : String(error);
}
if (caught.length === 0) {
  throw new Error('非法字节码应抛错');
}
console.log('非法输入被拒绝:', caught.slice(0, 60));

// 4) 缺省示例程序清单（供 run_all.ts 复用）
console.log('默认示例程序:', defaultProgram);
