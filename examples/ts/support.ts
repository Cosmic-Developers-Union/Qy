// TypeScript 宿主示例共用的工具函数。
//
// 两个职责：
//   1. `compileWithQy()`：调用 Python 侧的 `qy export` 生成字节码 JSON（编译器只有
//      Python 实现；TypeScript 宿主只执行字节码）；
//   2. 共用的常量与输出格式助手。

import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { spawnSync } from 'node:child_process';

/** 仓库根目录（examples/ts/ 的上两级）。 */
export const REPO_ROOT = new URL('../../', import.meta.url).pathname;

/** 默认示例程序：宿主前置算术（返回 42）。 */
export const defaultProgram = 'examples/qy/validation/00_host_arithmetic.qy';

/**
 * 用 `qy export` 把 Qy 源码编译成字节码 JSON，返回临时文件路径。
 *
 * 注意本工作区 uv 默认缓存只读，因此显式指定 `UV_CACHE_DIR`。
 */
export function compileWithQy(programPath: string): string {
  const outDir = mkdtempSync(join(tmpdir(), 'qy-ts-example-'));
  const outPath = join(outDir, 'program.json');
  const result = spawnSync(
    'uv',
    ['run', '--no-sync', 'qy', 'export', programPath, '-o', outPath],
    {
      cwd: REPO_ROOT,
      env: { ...process.env, UV_CACHE_DIR: '/tmp/uv-cache' },
      encoding: 'utf8',
    },
  );
  if (result.status !== 0) {
    throw new Error(
      `qy export failed for ${programPath}:\n${result.stderr || result.stdout}`,
    );
  }
  return outPath;
}

/** 包一层简单的断言，示例里失败要显式报错。 */
export function expectEqual(actual: string, expected: string, label: string): void {
  if (actual !== expected) {
    throw new Error(`${label}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
  }
}
