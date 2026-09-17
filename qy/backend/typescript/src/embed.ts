// 嵌入式宿主 API。
//
// 这是本项目（Qy 作为可嵌入语言）的最小宿主接口：
//   - `createVm()`：从字节码 JSON 或已装载程序创建一个 VM 句柄；
//   - `evalBytecode()`：一次性求值；
//   - `registerHostFunction()`：把一个宿主函数注册成 Qy 符号空间的纯算子。
//
// 宿主函数按 `PureOperatorValue` 语义接入：参数已经是求值后的 Qy 值，
// 返回值必须是 Qy 值（宿主原语应先用 `values.ts` 的构造器包成语义值）。

import { isDefinitionArtifact, formatValue } from './display.ts';
import { loadBytecodeJson, type BytecodeProgram } from './bytecode.ts';
import { Env } from './environment.ts';
import { PureOperatorValue, type QyValue } from './values.ts';
import { RegisterVirtualMachine } from './vm.ts';
import { createStandardEnvironment, resetModuleRegistry } from './stdlib/index.ts';

export { RegisterVirtualMachine } from './vm.ts';
export { createStandardEnvironment, resetModuleRegistry } from './stdlib/index.ts';
export * as values from './values.ts';
export { formatValue, isDefinitionArtifact } from './display.ts';
// 宿主接管输出：嵌入式场景常需要把 Qy 的 print/display 输出收进字符串或日志。
export { getOutputWriter, setOutputWriter } from './stdlib/io.ts';
export type { OutputWriter } from './stdlib/io.ts';
export { loadBytecodeJson } from './bytecode.ts';
export type { BytecodeProgram } from './bytecode.ts';

/** 一个可复用的 VM 句柄。 */
export class QyVm {
  readonly vm: RegisterVirtualMachine;
  readonly env: Env;

  constructor(program: BytecodeProgram, env?: Env) {
    this.env = env ?? createStandardEnvironment();
    this.vm = new RegisterVirtualMachine(program, this.env);
  }

  /** 注册宿主函数（纯算子）。可以是 async 函数：VM 会 await 返回值。 */
  registerHostFunction(name: string, fn: (...args: QyValue[]) => QyValue | Promise<QyValue>): void {
    this.env.define(name, new PureOperatorValue(name, fn));
  }

  /** 定义 Qy 值（例如常量或配置）。 */
  define(name: string, value: QyValue): void {
    this.env.define(name, value);
  }

  /** 运行程序，返回 APPEND_RESULT 收集到的全部结果（未过滤）。 */
  async run(): Promise<QyValue[]> {
    return await this.vm.evaluateProgram();
  }

  /** 运行并返回 `qy run` 会打印的文本行（跳过绑定形式产物）。 */
  async runLines(): Promise<string[]> {
    const results = await this.run();
    return results.filter((value) => !isDefinitionArtifact(value)).map(formatValue);
  }
}

/** 创建 VM；`program` 可以是 JSON 文本或已装载程序。 */
export function createVm(program: string | BytecodeProgram, env?: Env): QyVm {
  const parsed = typeof program === 'string' ? loadBytecodeJson(program) : program;
  return new QyVm(parsed, env);
}

/** 一次性求值，返回结果列表。 */
export async function evalBytecode(
  program: string | BytecodeProgram,
  env?: Env,
): Promise<QyValue[]> {
  return await createVm(program, env).run();
}

/** 便捷函数形式的宿主函数注册。 */
export function registerHostFunction(
  vm: QyVm,
  name: string,
  fn: (...args: QyValue[]) => QyValue | Promise<QyValue>,
): void {
  vm.registerHostFunction(name, fn);
}
