#!/usr/bin/env bun
// 运行全部 TypeScript 宿主示例（`make examples-ts` 与 CI 用）。
//
//   bun examples/ts/run_all.ts
//
// 每个示例都是独立进程：任何一个失败即整体失败（退出码非 0）。

import { spawnSync } from 'node:child_process';
import { readdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const examples = readdirSync(here)
  .filter((name) => name.endsWith('.ts') && !['run_all.ts', 'support.ts'].includes(name))
  .sort();

let failed = 0;
for (const example of examples) {
  const path = join(here, example);
  const result = spawnSync('bun', [path], { encoding: 'utf8' });
  if (result.status === 0) {
    console.log(`[ok] examples/ts/${example}`);
  } else {
    failed += 1;
    console.error(`[fail] examples/ts/${example}`);
    console.error(result.stdout);
    console.error(result.stderr);
  }
}

console.log(`examples/ts: ${examples.length - failed}/${examples.length} 通过`);
process.exitCode = failed === 0 ? 0 : 1;
