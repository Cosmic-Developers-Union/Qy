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
//   bun scripts/conformance.ts                 # 全量，输出通过数与失败清单
//   bun scripts/conformance.ts --verbose       # 附带期望/实际片段
//   bun scripts/conformance.ts --filter=effect # 只跑文件名匹配的语料
//   bun scripts/conformance.ts --keep          # 保留临时目录
//
// 注意：Python 命令必须带 UV_CACHE_DIR=/tmp/uv-cache（默认 uv 缓存只读）。

import { mkdtempSync, readdirSync, readFileSync, rmSync, writeFileSync, existsSync, mkdirSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';

const HERE = import.meta.dir;
const ROOT = resolve(HERE, '..', '..', '..', '..');
const CORPUS = join(ROOT, 'tests', 'qy');
const VM = join(ROOT, 'qy', 'backend', 'typescript', 'bin', 'qyvm.ts');

interface Args {
  verbose: boolean;
  keep: boolean;
  filter: string | null;
  listOnly: boolean;
}

function parseArgs(argv: string[]): Args {
  const args: Args = { verbose: false, keep: false, filter: null, listOnly: false };
  for (const item of argv) {
    if (item === '--verbose' || item === '-v') args.verbose = true;
    else if (item === '--keep') args.keep = true;
    else if (item === '--list') args.listOnly = true;
    else if (item.startsWith('--filter=')) args.filter = item.slice('--filter='.length);
  }
  return args;
}

interface RunResult {
  code: number;
  stdout: string;
  stderr: string;
}

function run(command: string[], env: Record<string, string> = {}): RunResult {
  const proc = Bun.spawnSync(command, {
    cwd: ROOT,
    env: { ...process.env, UV_CACHE_DIR: '/tmp/uv-cache', ...env },
    stdout: 'pipe',
    stderr: 'pipe',
  });
  return {
    code: proc.exitCode ?? -1,
    stdout: proc.stdout.toString(),
    stderr: proc.stderr.toString(),
  };
}

function firstDifference(expected: string, actual: string, limit = 3): string {
  const expectedLines = expected.split('\n');
  const actualLines = actual.split('\n');
  const lines: string[] = [];
  const max = Math.max(expectedLines.length, actualLines.length);
  for (let index = 0; index < max && lines.length < limit; index += 1) {
    if (expectedLines[index] !== actualLines[index]) {
      lines.push(
        `      line ${index + 1}: expected ${JSON.stringify(expectedLines[index] ?? '<eof>')}` +
          ` / actual ${JSON.stringify(actualLines[index] ?? '<eof>')}`,
      );
    }
  }
  return lines.join('\n');
}

async function main(): Promise<number> {
  const args = parseArgs(process.argv.slice(2));
  const files = readdirSync(CORPUS)
    .filter((name) => name.endsWith('.qy'))
    .filter((name) => args.filter === null || name.includes(args.filter))
    .sort();

  const workdir = mkdtempSync(join(tmpdir(), 'qy-conformance-'));
  const jsonDir = join(workdir, 'json');
  mkdirSync(jsonDir, { recursive: true });

  const failures: { name: string; reason: string; detail: string }[] = [];
  let passed = 0;
  let total = 0;

  for (const file of files) {
    total += 1;
    const name = file.replace(/\.qy$/, '');
    const source = join(CORPUS, file);

    const expectedRun = run(['uv', 'run', '--no-sync', 'qy', 'run', source]);
    if (expectedRun.code !== 0) {
      failures.push({
        name,
        reason: 'Python `qy run` 失败',
        detail: expectedRun.stderr.trim().split('\n').slice(0, 3).join('\n'),
      });
      continue;
    }

    const jsonPath = join(jsonDir, `${name}.json`);
    const exportRun = run(['uv', 'run', '--no-sync', 'qy', 'export', source, '-o', jsonPath]);
    if (!existsSync(jsonPath)) {
      failures.push({
        name,
        reason: 'Python `qy export` 未产出 JSON',
        detail: exportRun.stderr.trim().split('\n').slice(0, 3).join('\n'),
      });
      continue;
    }

    const actualRun = run(['bun', VM, jsonPath]);
    if (actualRun.code !== 0) {
      failures.push({
        name,
        reason: 'TS VM 非零退出',
        detail: actualRun.stderr.trim().split('\n').slice(0, 6).join('\n'),
      });
      continue;
    }

    if (actualRun.stdout === expectedRun.stdout) {
      passed += 1;
    } else {
      failures.push({
        name,
        reason: '输出不一致',
        detail: firstDifference(expectedRun.stdout, actualRun.stdout),
      });
    }
  }

  if (!args.keep) rmSync(workdir, { recursive: true, force: true });
  else process.stdout.write(`临时目录保留：${workdir}\n`);

  process.stdout.write(`\npassed ${passed}/${total}\n`);
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
