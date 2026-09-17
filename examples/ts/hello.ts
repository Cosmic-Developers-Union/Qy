#!/usr/bin/env bun
// 示例 1：把 Qy 程序编成字节码，再用 TypeScript 虚拟机执行（最小嵌入式用法）。
//
//   bun examples/ts/hello.ts                  # 自动用 qy export 生成字节码
//   bun examples/ts/hello.ts prog.json        # 直接执行已有字节码
//
// 说明：编译器（前端/中端）目前只有 Python 实现，因此这里调用 `qy export` 产出
// 跨宿主共享的字节码 JSON；TypeScript 侧只负责**执行**（寄存器虚拟机）。

import { createVm } from '../../qy/backend/typescript/src/embed.ts';
import { compileWithQy, defaultProgram, formatLines } from './support.ts';

const target = process.argv[2];
const bytecodePath = target ?? (await compileWithQy(defaultProgram));

const vm = createVm(await Bun.file(bytecodePath).text());
const lines = await vm.runLines();

for (const line of lines) {
  console.log(line);
}

// 退出码语义与 `qy run` 一致：成功打印结果即 0。
process.exitCode = lines.length > 0 ? 0 : 1;
