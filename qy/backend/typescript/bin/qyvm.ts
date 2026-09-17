#!/usr/bin/env bun
// `qyvm` 命令行：执行 `qy export` 产出的字节码 JSON。
//
//   bun qy/backend/typescript/bin/qyvm.ts prog.json
//   bun qy/backend/typescript/bin/qyvm.ts -   # 从 stdin 读取
//
// 输出格式与 `qy run` 完全一致：对每个顶层结果，跳过绑定形式产物，
// 其余按 `qy/display.py::format_value` 打印并换行。

import { readFileSync } from 'node:fs';
import { formatValue, isDefinitionArtifact } from '../src/display.ts';
import { createVm } from '../src/embed.ts';

function readStdin(): string {
  return readFileSync(0, 'utf8');
}

async function main(): Promise<number> {
  const target = process.argv[2];
  if (target === undefined) {
    process.stderr.write('usage: qyvm <program.json | ->\n');
    return 2;
  }
  let text: string;
  try {
    text = target === '-' ? readStdin() : readFileSync(target, 'utf8');
  } catch (error) {
    process.stderr.write(`qyvm: cannot read ${target}: ${String(error)}\n`);
    return 2;
  }

  try {
    const vm = createVm(text);
    const results = await vm.run();
    for (const value of results) {
      if (isDefinitionArtifact(value)) continue;
      process.stdout.write(`${formatValue(value)}\n`);
    }
    return 0;
  } catch (error) {
    const message = error instanceof Error ? `${error.name}: ${error.message}` : String(error);
    process.stderr.write(`${message}\n`);
    return 1;
  }
}

process.exitCode = await main();
