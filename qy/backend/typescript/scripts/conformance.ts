#!/usr/bin/env bun
// 语料一致性（conformance）脚本。
//
// 对 `tests/qy/*.qy` 的每个文件执行题目给定的三方流程：
//
//   1. uv run --no-sync qy run  FILE            → 期望输出（Python 参考语义）
//   2. uv run --no-sync qy export FILE -o TMP   → 字节码 JSON（唯一契约）
//   3. bun bin/qyvm.ts TMP                      → 本 TS VM 输出
//   4. diff 1 与 3
//
// 用法：
//   bun scripts/conformance.ts                          # 全量（compat）
//   bun scripts/conformance.ts --verbose                # 附带期望/实际片段
//   bun scripts/conformance.ts --filter=effect          # 只跑文件名匹配的语料
//   bun scripts/conformance.ts --dialect abstract-machine
//   bun scripts/conformance.ts --keep                   # 保留临时目录
//
// `--dialect abstract-machine` 时，参考输出仍取 Python `qy run`（compat），
// 因为两种 dialect 的语义必须等价（tests/test_abstract_machine_vm.py 的既有
// 差分结论）；导出改用 `qy export --dialect abstract-machine`。
//
// 注意：Python 命令必须带 UV_CACHE_DIR=/tmp/uv-cache（默认 uv 缓存只读）。

import { mkdtempSync, readdirSync, rmSync, mkdirSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { basename, join } from 'node:path';

import { CORPORA, CORPUS, parseArgs, runCase, type CaseStatus } from './harness.ts';

const STATUS_REASON: Record<Exclude<CaseStatus, 'pass' | 'exchange-unencodable'>, string> = {
  'python-failed': 'Python `qy run` 失败',
  'export-failed': 'Python `qy export` 未产出 JSON',
  'vm-failed': 'TS VM 非零退出',
  mismatch: '输出不一致',
};

/**
 * `exchange-unencodable`：Python 导出的 JSON 含 `{"type":"unknown"}`，Python 自己的
 * `load_bytecode_json` 也无法读入 —— 属于交换格式缺口，如实排除，不计入失败。
 */
const EXCLUDED_REASON = '交换格式无法编码（Python 侧 load_bytecode_json 同样失败）';

async function main(): Promise<number> {
  const args = parseArgs(process.argv.slice(2));
  const files: { name: string; source: string }[] = [];
  for (const dir of CORPORA) {
    const prefix = dir === CORPUS ? '' : `${basename(dir)}__`;
    for (const entry of readdirSync(dir)
      .filter((name) => name.endsWith('.qy'))
      .sort()) {
      const name = prefix + entry.replace(/\.qy$/, '');
      if (args.filter !== null && !name.includes(args.filter)) continue;
      files.push({ name, source: join(dir, entry) });
    }
  }

  const workdir = mkdtempSync(join(tmpdir(), 'qy-conformance-'));
  const jsonDir = join(workdir, 'json');
  mkdirSync(jsonDir, { recursive: true });

  const failures: { name: string; reason: string; detail: string }[] = [];
  const excluded: { name: string; detail: string }[] = [];
  let passed = 0;
  let total = 0;

  for (const file of files) {
    total += 1;
    const name = file.name;
    const source = file.source;
    const outcome = runCase(source, {
      jsonPath: join(jsonDir, `${name}.json`),
      dialect: args.dialect,
    });
    if (outcome.status === 'pass') {
      passed += 1;
      continue;
    }
    if (outcome.status === 'exchange-unencodable') {
      excluded.push({ name, detail: outcome.detail });
      continue;
    }
    failures.push({
      name,
      reason: STATUS_REASON[outcome.status],
      detail: outcome.detail,
    });
  }

  if (!args.keep) rmSync(workdir, { recursive: true, force: true });
  else process.stdout.write(`临时目录保留：${workdir}\n`);

  process.stdout.write(`\ndialect: ${args.dialect}\n`);
  process.stdout.write(`passed ${passed}/${total}`);
  if (excluded.length > 0) process.stdout.write(`（排除 ${excluded.length}）`);
  process.stdout.write('\n');
  if (excluded.length > 0) {
    process.stdout.write(`\n排除清单（${excluded.length}，${EXCLUDED_REASON}）：\n`);
    for (const item of excluded) {
      process.stdout.write(`  - ${item.name}\n`);
      if (args.verbose && item.detail) process.stdout.write(`      ${item.detail}\n`);
    }
  }
  if (failures.length > 0 && !args.listOnly) {
    process.stdout.write(`\n失败清单（${failures.length}）：\n`);
    for (const failure of failures) {
      process.stdout.write(`  - ${failure.name}: ${failure.reason}\n`);
      if (args.verbose && failure.detail) {
        process.stdout.write(`${failure.detail}\n`);
      }
    }
  } else if (failures.length > 0) {
    process.stdout.write(`失败：${failures.map((failure) => failure.name).join(', ')}\n`);
  }

  return failures.length === 0 ? 0 : 1;
}

process.exitCode = await main();
