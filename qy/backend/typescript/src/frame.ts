// VM 帧与函数值。
//
// 对应 Python：
//   - `qy/vm/bytecode.py::BytecodeFunctionValue`
//   - `qy/vm/instance/machine.py::_Frame` / `_EffectFrame` / `_HandlerRecord`

import type { BytecodeFunction, BytecodeProgram, HandlerSpec } from './bytecode.ts';
import type { QyEffectSignal } from './errors.ts';
import type { Env } from './environment.ts';
import { listToChain } from './values.ts';
import type { QyValue } from './values.ts';

/**
 * 一个可调用的字节码函数值（闭包）。
 *
 * Python 的 `BytecodeFunctionValue(function, closure, program=None)` 在每次
 * `_run_function` 时按 `function.name` 决定是否新建子空间：
 * `<main>` / `<module-body>` 直接用闭包空间，其余用 `closure.child(params)`。
 */
export class BytecodeFunctionValue {
  constructor(
    readonly fn: BytecodeFunction,
    readonly closure: Env,
    readonly program?: BytecodeProgram,
  ) {}
}

/** 一条 HANDLER_PUSH 记录（abstract-machine dialect，语料未使用但要保留语义）。 */
export interface HandlerRecord {
  handlerId: number;
  target: number;
  parentId: number | null;
  specs: HandlerSpec[];
}

/** 执行帧。字段与 Python `_Frame` 一一对应。 */
export interface Frame {
  functionValue: BytecodeFunctionValue;
  fn: BytecodeFunction;
  pc: number;
  registers: QyValue[];
  env: Env;
  parents: Env[];
  results: QyValue[];
  handlers: HandlerRecord[];
  pendingEffect: [number, QyEffectSignal] | null;
}

/** `_run_function` 的返回：函数结束时的值 + 顶层结果列表。 */
export class FrameResult {
  constructor(
    readonly value: QyValue,
    readonly results: QyValue[],
  ) {}
}

/** 创建执行帧（对应 `_make_frame`）。 */
export function makeFrame(
  functionValue: BytecodeFunctionValue,
  args: QyValue[],
  onArityError: (message: string) => never,
): Frame {
  const fn = functionValue.fn;
  const restParam = fn.restParam;
  const fixedCount = fn.params.length;
  if (restParam === null && args.length !== fixedCount) {
    onArityError(`${fn.name} expects ${fixedCount} arguments, got ${args.length}`);
  }
  if (restParam !== null && args.length < fixedCount) {
    onArityError(`${fn.name} expects at least ${fixedCount} arguments, got ${args.length}`);
  }
  let env: Env;
  if (fn.name === '<main>' || fn.name === '<module-body>') {
    env = functionValue.closure;
  } else {
    const bindings = new Map<string, QyValue>();
    fn.params.forEach((param, index) => bindings.set(param, args[index]));
    if (restParam !== null) {
      bindings.set(restParam, listToChain(args.slice(fixedCount)));
    }
    env = functionValue.closure.child(bindings);
  }
  return {
    functionValue,
    fn,
    pc: 0,
    registers: new Array<QyValue>(fn.registerCount).fill(null),
    env,
    parents: [],
    results: [],
    handlers: [],
    pendingEffect: null,
  };
}

/** 深拷贝帧寄存器快照（effect 捕获用）。 */
export function cloneRegisters(registers: QyValue[]): QyValue[] {
  return registers.slice();
}
