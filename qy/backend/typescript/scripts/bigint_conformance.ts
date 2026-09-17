#!/usr/bin/env bun
// 大整数（BigInt 语义）一致性验证。
//
// 背景：Python 侧 `IntValue` 是任意精度 int（`qy/sem/core.py`），而 TS 宿主只有
// double。本脚本用同一套三方流程（Python `qy run` 参考 → `qy export` JSON →
// `bun bin/qyvm.ts`）逐字节比对以下用例，覆盖：
//
//   - 超过 2^53 的加减乘、比较、取模、除法；
//   - 阶乘（30!）与累加（超过 2^32）；
//   - `reify` 的大整数 symbol 拼写（验证不会输出 `123n`）；
//   - 大整数与浮点混合时的 `unsupported-operation`（用 handler 收敛为确定值）；
//   - 浮点仍走 Python repr 规则（回归保护）。
//
// 用法：
//   bun scripts/bigint_conformance.ts
//   bun scripts/bigint_conformance.ts --verbose
//   bun scripts/bigint_conformance.ts --dialect abstract-machine
//
// 注意：Python 命令必须带 UV_CACHE_DIR=/tmp/uv-cache（默认 uv 缓存只读）。

import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { parseArgs, runCase, type CaseStatus } from './harness.ts';

interface BigIntCase {
  name: string;
  source: string;
}

/** 覆盖大整数正确性 / 定宽溢出 / 混合类型错误的最小用例集。 */
const CASES: BigIntCase[] = [
  // 2^53 = 9007199254740992；9007199254740993 在 double 里不可表示。
  { name: 'add_2p53', source: '(+ 9007199254740993 1)\n' },
  {
    name: 'mul_2p53',
    source: '(* 9007199254740993 9007199254740993)\n',
  },
  { name: 'neg_2p53', source: '(- 0 9007199254740993)\n' },
  {
    name: 'factorial_30',
    source: [
      '(defun f (n acc)',
      '  (cond ((= n 0) acc)',
      '        (T (f (- n 1) (* acc n)))))',
      '(f 30 1)',
      '',
    ].join('\n'),
  },
  {
    // 结果 5000050000 > 2^32，验证累加不会掉回 32 位。
    name: 'accumulate_100000',
    source: [
      '(defun g (n acc)',
      '  (cond ((= n 0) acc)',
      '        (T (g (- n 1) (+ acc n)))))',
      '(g 100000 0)',
      '',
    ].join('\n'),
  },
  { name: 'ordering_big', source: '(< 100000000000000000000 100000000000000000001)\n' },
  { name: 'equality_big', source: '(= 9007199254740993 9007199254740993)\n' },
  {
    name: 'modulo_big',
    source: '(mod 100000000000000000000000000007 97)\n',
  },
  {
    // BigInt `/` 向零截断；Python 二元分支同语义。
    name: 'division_big',
    source: '(/ -100000000000000000000 7)\n',
  },
  {
    // 运行时（非常量折叠）的异号大整数除法：Python 走 `int(a/b)` float 路径，
    // 必须逐字节复刻，验证 TS 没有"改成精确截断"。
    name: 'division_runtime_big',
    source: [
      '(defun build (n acc)',
      '  (cond ((= n 0) acc)',
      '        (T (build (- n 1) (* acc 10)))))',
      '(defun h (a b) (/ a b))',
      '(h (- 0 (build 20 1)) 7)',
      '',
    ].join('\n'),
  },
  {
    // reify 的整数 symbol 拼写：必须是十进制，不能出现宿主 `123n`。
    name: 'reify_big',
    source: '(reify 9007199254740993)\n',
  },
  {
    // 大整数 + 浮点：同 concrete 类型检查触发 unsupported-operation，
    // 用 handler 收敛为确定值，避免把错误信息差异当成语义差异。
    name: 'mixed_int_float_error',
    source: [
      '(defeffect unsupported-operation)',
      '(handle (+ 1.5 9007199254740993)',
      '        ((unsupported-operation (arg k) "mixed-type-error")))',
      '',
    ].join('\n'),
  },
  { name: 'float_repr_regression', source: '(+ 1.5 2.5)\n' },
];

const STATUS_REASON: Record<Exclude<CaseStatus, 'pass' | 'exchange-unencodable'>, string> = {
  'python-failed': 'Python `qy run` 失败',
  'export-failed': 'Python `qy export` 未产出 JSON',
  'vm-failed': 'TS VM 非零退出',
  mismatch: '输出不一致',
};

async function main(): Promise<number> {
  const args = parseArgs(process.argv.slice(2));
  const workdir = mkdtempSync(join(tmpdir(), 'qy-bigint-'));
  const jsonDir = join(workdir, 'json');
  mkdirSync(jsonDir, { recursive: true });

  const failures: { name: string; reason: string; detail: string; expected: string; actual: string }[] = [];
  const excluded: string[] = [];
  let passed = 0;

  for (const testCase of CASES) {
    const sourcePath = join(workdir, `${testCase.name}.qy`);
    writeFileSync(sourcePath, testCase.source, 'utf8');
    const outcome = runCase(sourcePath, {
      jsonPath: join(jsonDir, `${testCase.name}.json`),
      dialect: args.dialect,
    });
    if (outcome.status === 'pass') {
      passed += 1;
      if (args.verbose) {
        process.stdout.write(`  ok ${testCase.name}: ${JSON.stringify(outcome.expected)}\n`);
      }
      continue;
    }
    if (outcome.status === 'exchange-unencodable') {
      excluded.push(testCase.name);
      continue;
    }
    failures.push({
      name: testCase.name,
      reason: STATUS_REASON[outcome.status],
      detail: outcome.detail,
      expected: outcome.expected,
      actual: outcome.actual,
    });
  }

  if (!args.keep) rmSync(workdir, { recursive: true, force: true });
  else process.stdout.write(`临时目录保留：${workdir}\n`);

  process.stdout.write(`\ndialect: ${args.dialect}\n`);
  process.stdout.write(`passed ${passed}/${CASES.length}`);
  if (excluded.length > 0) process.stdout.write(`（排除 ${excluded.length}: ${excluded.join(', ')}）`);
  process.stdout.write('\n');
  if (failures.length > 0) {
    process.stdout.write(`\n失败清单（${failures.length}）：\n`);
    for (const failure of failures) {
      process.stdout.write(`  - ${failure.name}: ${failure.reason}\n`);
      process.stdout.write(`      expected ${JSON.stringify(failure.expected)}\n`);
      process.stdout.write(`      actual   ${JSON.stringify(failure.actual)}\n`);
      if (failure.detail) process.stdout.write(`${failure.detail}\n`);
    }
  }

  return failures.length === 0 ? 0 : 1;
}

process.exitCode = await main();
