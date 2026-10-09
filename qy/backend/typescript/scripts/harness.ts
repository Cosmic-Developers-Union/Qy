// conformance 公共设施：Python 参考输出、字节码导出、TS VM 执行、逐字节 diff。
//
// 供 `scripts/conformance.ts`（tests/qy 语料）与 `scripts/bigint_conformance.ts`
// （内联大整数用例）复用。契约流程固定为：
//
//   1. uv run --no-sync qy run  FILE            → 期望输出（compat 语义真源）
//   2. uv run --no-sync qy export FILE -o TMP   → 字节码 JSON（唯一契约）
//   3. bun bin/qyvm.ts TMP                      → 本 TS VM 输出
//   4. diff 1 与 3
//
// 注意：Python 命令必须带 UV_CACHE_DIR=/tmp/uv-cache（默认 uv 缓存只读）。

import { existsSync, readFileSync } from 'node:fs';
import { join, resolve } from 'node:path';

export const HERE = import.meta.dir;
export const ROOT = resolve(HERE, '..', '..', '..', '..');
export const CORPUS = join(ROOT, 'tests', 'qy');
/**
 * 额外语料：Qy-in-Qy 解释器用例，覆盖 hygiene / effect / dotted pair 等
 * `tests/qy` 未覆盖的行为。conformance 把两者合并为一个门禁。
 */
export const CASE_CORPUS = join(ROOT, 'meta-interp', 'cases');
export const CORPORA = [CORPUS, CASE_CORPUS] as const;
export const VM = join(ROOT, 'qy', 'backend', 'typescript', 'bin', 'qyvm.ts');

/** 允许的 LIR dialect，与 `qy/cli/commands/export.py` 的 choice 保持一致。 */
export const DIALECTS = ['compat', 'abstract-machine'] as const;
export type Dialect = (typeof DIALECTS)[number];

export interface RunResult {
  code: number;
  stdout: string;
  stderr: string;
}

export function run(command: string[], env: Record<string, string> = {}): RunResult {
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

export function firstDifference(expected: string, actual: string, limit = 3): string {
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

export type CaseStatus =
  | 'pass'
  | 'python-failed'
  | 'export-failed'
  | 'exchange-unencodable'
  | 'vm-failed'
  | 'mismatch';

export interface CaseOutcome {
  status: CaseStatus;
  /** Python compat `qy run` 的输出。 */
  expected: string;
  /** TS VM 的输出。 */
  actual: string;
  detail: string;
}

export interface CaseOptions {
  /** 目标 JSON 路径（放在调用方的临时目录里）。 */
  jsonPath: string;
  dialect: Dialect;
  /** 额外传给 `qy export` 的参数（如 `--dialect abstract-machine`）。 */
  expectedCommand?: string[];
}

/**
 * 跑单个源文件的完整对拍流程。
 *
 * 期望输出始终取 Python `qy run`（默认 compat）——两种 dialect 的语义必须等价
 * （tests/test_abstract_machine_vm.py 已有既有差分结论），所以 compat 输出就是
 * abstract-machine 的参考。
 */
export function runCase(sourcePath: string, options: CaseOptions): CaseOutcome {
  const expectedRun = run(options.expectedCommand ?? ['uv', 'run', '--no-sync', 'qy', 'run', sourcePath]);
  if (expectedRun.code !== 0) {
    return {
      status: 'python-failed',
      expected: '',
      actual: '',
      detail: expectedRun.stderr.trim().split('\n').slice(0, 3).join('\n'),
    };
  }
  const expected = expectedRun.stdout;

  const exportArgs = ['uv', 'run', '--no-sync', 'qy', 'export'];
  if (options.dialect !== 'compat') exportArgs.push('--dialect', options.dialect);
  exportArgs.push(sourcePath, '-o', options.jsonPath);
  const exportRun = run(exportArgs);
  if (!existsSync(options.jsonPath)) {
    return {
      status: 'export-failed',
      expected,
      actual: '',
      detail: exportRun.stderr.trim().split('\n').slice(0, 3).join('\n'),
    };
  }

  // 交换格式自身的缺口：`abstract-machine` 的 `SLOT_COMPLETE` 携带
  // `LIRBindingAddr`，序列化器把它写成 `{"type":"unknown", ...}`。Python 自己的
  // `load_bytecode_json` 同样会抛 ValueError，所以这不是 TS VM 的缺陷，而是
  // Python 侧交换格式无法承载该 dialect 的这一类操作数。此类语料如实排除。
  const jsonText = readFileSync(options.jsonPath, 'utf8');
  if (/"type"\s*:\s*"unknown"/.test(jsonText)) {
    return {
      status: 'exchange-unencodable',
      expected,
      actual: '',
      detail:
        'exchanged JSON contains {"type":"unknown"} (LIRBindingAddr); ' +
        "Python's own load_bytecode_json raises ValueError for it",
    };
  }

  const actualRun = run(['bun', VM, options.jsonPath]);
  if (actualRun.code !== 0) {
    return {
      status: 'vm-failed',
      expected,
      actual: actualRun.stdout,
      detail: actualRun.stderr.trim().split('\n').slice(0, 6).join('\n'),
    };
  }

  if (actualRun.stdout === expected) {
    return { status: 'pass', expected, actual: actualRun.stdout, detail: '' };
  }
  return {
    status: 'mismatch',
    expected,
    actual: actualRun.stdout,
    detail: firstDifference(expected, actualRun.stdout),
  };
}

export interface Args {
  verbose: boolean;
  keep: boolean;
  filter: string | null;
  listOnly: boolean;
  dialect: Dialect;
}

export function parseArgs(argv: string[], defaults: Partial<Args> = {}): Args {
  const args: Args = {
    verbose: false,
    keep: false,
    filter: null,
    listOnly: false,
    dialect: 'compat',
    ...defaults,
  };
  for (let index = 0; index < argv.length; index += 1) {
    const item = argv[index];
    if (item === '--verbose' || item === '-v') args.verbose = true;
    else if (item === '--keep') args.keep = true;
    else if (item === '--list') args.listOnly = true;
    else if (item.startsWith('--filter=')) args.filter = item.slice('--filter='.length);
    else if (item === '--filter') args.filter = argv[++index] ?? null;
    else if (item.startsWith('--dialect=')) args.dialect = item.slice('--dialect='.length) as Dialect;
    else if (item === '--dialect') args.dialect = (argv[++index] ?? 'compat') as Dialect;
  }
  if (!DIALECTS.includes(args.dialect)) {
    throw new Error(`unknown dialect '${args.dialect}'; expected one of ${DIALECTS.join(', ')}`);
  }
  return args;
}
