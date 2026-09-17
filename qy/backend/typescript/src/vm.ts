// 寄存器虚拟机：指令分派与语义。
//
// 这是 `qy/vm/instance/machine.py::RegisterVirtualMachine` 的 TypeScript 移植。
// 移植原则是**逐指令对齐 Python 行为**，不做"更合理"的改写；每条 case 上标注了
// 对应 Python 位置。差异只出现在两处（均在最终报告里说明）：
//
//   1. `LOAD_ENV` 会使用交换格式的 `hygiene_bindings`（Python VM 丢弃该字段）；
//   2. `FROM_IMPORT` 对"既不在 exports 也不在 macro_exports"的名字选择跳过，
//      因为交换格式不携带 macro_exports（Python 会抛 KeyError）。
//
// 并发（`parallel` / `all` / `race`）：见本文件 `-- 并发形式` 一节的详细边界
// 说明。简言之：只有在**可静态证明 thunk 子树不触发 effect、不做 IO、不改共享
// 状态**时才用 `Promise.allSettled` / `Promise.race` 真正并发；否则顺序执行。

import {
  QyAggregateError,
  QyEffectSignal,
  QyError,
  QyResolveError,
  QyRuntimeError,
  QyTypeError,
  EvaluationError,
} from './errors.ts';
import type { BytecodeFunction, BytecodeProgram, HandlerSpec } from './bytecode.ts';
import { Env } from './environment.ts';
import { BytecodeFunctionValue, FrameResult, makeFrame, type Frame, type HandlerRecord } from './frame.ts';
import {
  Continuation,
  COMPILE_TIME_MACRO,
  Chain,
  EffectDefinition,
  ListValue,
  ModuleValue,
  PureOperatorValue,
  RawOperatorValue,
  QY_NIL,
  StringValue,
  Symbol,
  TupleValue,
  type QyValue,
} from './values.ts';
import { builtinModules, callBuiltin, createStandardEnvironment, lookupModule, registerModule } from './stdlib/index.ts';
import { normalizeArgument } from './stdlib/data.ts';
import { coreTruthy } from './stdlib/control.ts';
import { identityContinuation } from './stdlib/support.ts';
import { formatValue } from './display.ts';

/**
 * 并发安全判定用：有 IO / 副作用的 `CALL_BUILTIN` 下标。
 * 内建 ABI 顺序见 `stdlib/index.ts::BUILTIN_NAMES`：8 display、9 echo、
 * 10 newline、11 read、12 read-int。
 */
const CONCURRENCY_UNSAFE_BUILTINS = new Set([8, 9, 10, 11, 12]);

/** `LOAD_ENV` 读到这些有副作用的宿主算子时，thunk 视为不纯。 */
const CONCURRENCY_UNSAFE_SYMBOLS = new Set([
  'print',
  'echo',
  'display',
  'newline',
  'read',
  'read-int',
]);

/** effect 触发时的帧快照（对应 `machine.py::_EffectFrame`）。 */
interface EffectFrameSnapshot {
  registers: QyValue[];
  env: Env;
  pc: number;
  parents: Env[];
  results: QyValue[];
  functionValue: BytecodeFunctionValue;
  fn: BytecodeFunction;
  handlers: Frame['handlers'];
}

/** 寄存器 VM。 */
export class RegisterVirtualMachine {
  readonly program: BytecodeProgram;
  readonly env: Env;
  /** CACHE_EVAL 的共享缓存（对应 Python symbol-space 的 cache KV）。 */
  private readonly cache = new Map<string, QyValue>();

  constructor(program: BytecodeProgram, env?: Env) {
    this.program = program;
    this.env = env ?? createStandardEnvironment();
  }

  /** 求值整个程序，返回 APPEND_RESULT 收集到的结果列表。 */
  async evaluateProgram(): Promise<QyValue[]> {
    const mainFn = this.program.functions[this.program.main];
    if (!mainFn) throw new QyRuntimeError(`program has no function #${this.program.main}`);
    const main = new BytecodeFunctionValue(mainFn, this.env, this.program);
    const result = await this.runFunction(main, []);
    return result.results;
  }

  /** 求值并返回最后一个结果（`evaluate`）。 */
  async evaluate(): Promise<QyValue> {
    const results = await this.evaluateProgram();
    return results.length === 0 ? null : results[results.length - 1];
  }

  /** 执行一个函数体（对应 `_run_function`）。 */
  async runFunction(functionValue: BytecodeFunctionValue, args: QyValue[]): Promise<FrameResult> {
    let frame = makeFrame(functionValue, args, (name, expected, actual) => {
      throw new QyRuntimeError(`${name} expects ${expected} arguments, got ${actual}`);
    });
    for (;;) {
      const instruction = frame.fn.instructions[frame.pc];
      if (instruction === undefined) {
        // 指令耗尽（Python 会 IndexError；正常 emit 不会出现）
        return new FrameResult(null, frame.results);
      }
      frame.pc += 1;
      const result = await this.executeInstruction(frame, instruction);
      if (result instanceof FrameResult) return result;
      if (result !== null) frame = result;
    }
  }

  /** 单条指令分派（对应 `_execute_instruction`）。 */
  private async executeInstruction(
    frame: Frame,
    instruction: { opcode: string; operands: QyValue[] },
  ): Promise<FrameResult | Frame | null> {
    const operands = instruction.operands;
    const regs = frame.registers;
    const reg = (value: QyValue): number => value as number;

    switch (instruction.opcode) {
      case 'LOAD_HOST': {
        const [dest, value] = operands;
        regs[reg(dest)] = value;
        return null;
      }
      case 'LOAD_ENV': {
        const [dest, symbol] = operands;
        regs[reg(dest)] = this.resolveEnv(frame.env, symbol as Symbol);
        return null;
      }
      case 'MOVE': {
        const [dest, source] = operands;
        regs[reg(dest)] = regs[reg(source)];
        return null;
      }
      case 'STORE_LOCAL': {
        const [symbol, source] = operands;
        const value = regs[reg(source)];
        if (value !== COMPILE_TIME_MACRO) {
          frame.env.define((symbol as Symbol).name, value);
        }
        return null;
      }
      case 'DEFINE_ONCE': {
        const [symbol, source] = operands;
        const value = regs[reg(source)];
        if (value !== COMPILE_TIME_MACRO) {
          frame.env.defineOnce((symbol as Symbol).name, value);
        }
        return null;
      }
      case 'MAKE_FUNCTION': {
        const [dest, functionIndex] = operands;
        regs[reg(dest)] = new BytecodeFunctionValue(
          this.program.functions[reg(functionIndex)],
          frame.env,
          this.program,
        );
        return null;
      }
      case 'MAKE_MACRO': {
        const [dest] = operands;
        regs[reg(dest)] = COMPILE_TIME_MACRO;
        return null;
      }
      case 'ENTER_SCOPE': {
        frame.parents.push(frame.env);
        frame.env = frame.env.child();
        return null;
      }
      case 'EXIT_SCOPE': {
        const parent = frame.parents.pop();
        if (parent !== undefined) frame.env = parent;
        return null;
      }
      case 'SS_ENTER': {
        frame.parents.push(frame.env);
        frame.env = frame.env.child();
        return null;
      }
      case 'SS_LEAVE': {
        const parent = frame.parents.pop();
        if (parent !== undefined) frame.env = parent;
        return null;
      }
      case 'APPEND_RESULT': {
        const [source] = operands;
        const value = regs[reg(source)];
        frame.results.push(value === COMPILE_TIME_MACRO ? null : value);
        return null;
      }
      case 'BUILD_TUPLE': {
        const dest = operands[0];
        const values = operands.slice(1).map((item) => regs[reg(item)]);
        regs[reg(dest)] = values;
        return null;
      }
      case 'APPLY': {
        const [dest, funcReg, argsReg] = operands;
        const callee = regs[reg(funcReg)];
        const argsValue = regs[reg(argsReg)];
        const args = sequenceToArgs(argsValue);
        regs[reg(dest)] = await this.call(callee, args, frame.env);
        return null;
      }
      case 'RUNTIME_EVAL': {
        const [dest, formReg] = operands;
        const form = regs[reg(formReg)];
        regs[reg(dest)] = await this.evalForm(form, frame.env);
        return null;
      }
      case 'PARALLEL_GATHER': {
        const [dest, ...thunks] = operands;
        regs[reg(dest)] = await this.parallelGather(thunks.map((item) => reg(item)), frame.env, true);
        return null;
      }
      case 'ALL_GATHER': {
        const [dest, ...thunks] = operands;
        regs[reg(dest)] = await this.parallelGather(thunks.map((item) => reg(item)), frame.env, false);
        return null;
      }
      case 'RACE_FIRST': {
        const [dest, ...thunks] = operands;
        regs[reg(dest)] = await this.raceFirst(thunks.map((item) => reg(item)), frame.env);
        return null;
      }
      case 'DEFINE_MODULE': {
        const [dest, moduleName, functionIndex, exportNames] = operands;
        regs[reg(dest)] = await this.defineModule(
          (moduleName as Symbol).name,
          reg(functionIndex),
          frame.env,
          Array.isArray(exportNames) ? (exportNames as Symbol[]).map((item) => item.name) : [],
        );
        return null;
      }
      case 'FROM_IMPORT': {
        const [moduleName, specs] = operands;
        this.fromImport((moduleName as Symbol).name, Array.isArray(specs) ? specs : [], frame.env);
        return null;
      }
      case 'DEFEFFECT': {
        const [effectName, resumable] = operands;
        frame.env.define(
          (effectName as Symbol).name,
          new EffectDefinition((effectName as Symbol).name, Boolean(resumable)),
        );
        return null;
      }
      case 'PERFORM': {
        const [dest, effectSym, argReg] = operands;
        regs[reg(dest)] = await this.perform(
          frame,
          reg(dest),
          effectSym as Symbol,
          regs[reg(argReg)],
        );
        return null;
      }
      case 'HANDLE': {
        const [dest, bodyFnIdx, handlerSpecs] = operands;
        regs[reg(dest)] = await this.handle(
          reg(bodyFnIdx),
          Array.isArray(handlerSpecs) ? (handlerSpecs as HandlerSpec[]) : [],
          frame.env,
        );
        return null;
      }
      case 'RESUME': {
        const [dest, contReg, valueReg] = operands;
        const continuation = regs[reg(contReg)];
        const value = regs[reg(valueReg)];
        regs[reg(dest)] = await this.resume(continuation, value);
        return null;
      }
      case 'CONT_RESTORE': {
        const [contRegister, dstRegister, valueRegister] = operands;
        const continuation = regs[reg(contRegister)];
        const value = regs[reg(valueRegister)];
        if (!(continuation instanceof Continuation)) {
          throw new QyRuntimeError('CONT_RESTORE expects a continuation');
        }
        // 非终结：恢复点把值放进 dst，handler 体继续运行（同 compat RESUME）。
        regs[reg(dstRegister)] = (await continuation.resume(value)) as QyValue;
        return null;
      }
      case 'CONT_COPY': {
        const [dest, source] = operands;
        regs[reg(dest)] = regs[reg(source)];
        return null;
      }
      case 'JUMP': {
        const [target] = operands;
        frame.pc = reg(target);
        return null;
      }
      case 'JUMP_IF_FALSE': {
        const [source, target] = operands;
        if (!coreTruthy(regs[reg(source)])) frame.pc = reg(target);
        return null;
      }
      case 'CALL_BUILTIN': {
        // LIR selection 的产物：内建下标直接执行语言实现自身的算子体。
        const [dest, builtinId, argRegisters] = operands;
        const args = asNumberArray(argRegisters).map((item) => regs[item]);
        regs[reg(dest)] = callBuiltin(reg(builtinId), args);
        return null;
      }
      case 'CALL': {
        const [dest, calleeRegister, argRegisters] = operands;
        const args = asNumberArray(argRegisters).map((item) => regs[item]);
        const callee = regs[reg(calleeRegister)];
        try {
          regs[reg(dest)] = await this.call(callee, args, frame.env);
        } catch (error) {
          if (error instanceof QyEffectSignal && this.dispatchToHandler(frame, error)) {
            return null;
          }
          throw error;
        }
        return null;
      }
      case 'TAIL_CALL': {
        const [calleeRegister, argRegisters] = operands;
        const args = asNumberArray(argRegisters).map((item) => regs[item]);
        const callee = regs[reg(calleeRegister)];
        if (callee instanceof BytecodeFunctionValue) {
          return makeFrame(callee, args, (name, expected, actual) => {
            throw new QyRuntimeError(`${name} expects ${expected} arguments, got ${actual}`);
          });
        }
        return new FrameResult(await this.call(callee, args, frame.env), []);
      }
      case 'RETURN': {
        const [source] = operands;
        const value = regs[reg(source)];
        return new FrameResult(value === COMPILE_TIME_MACRO ? null : value, frame.results);
      }
      case 'RAISE_EFFECT': {
        const [effectNameSym, payloadRegister, resumable] = operands;
        const effectName = (effectNameSym as Symbol).name;
        const payload = regs[reg(payloadRegister)];
        throw new QyEffectSignal(
          effectName,
          payload,
          identityContinuation(effectName, Boolean(resumable)),
          Boolean(resumable),
        );
      }
      case 'HANDLER_PUSH': {
        const [handlerId, target, parentId, specs] = operands;
        const record: HandlerRecord = {
          handlerId: reg(handlerId),
          target: reg(target),
          parentId: parentId === null || parentId === undefined ? null : reg(parentId),
          specs: Array.isArray(specs) ? specs : [],
        };
        frame.handlers.push(record);
        return null;
      }
      case 'HANDLER_POP': {
        if (frame.handlers.length > 0) frame.handlers.pop();
        return null;
      }
      case 'EFFECT_UNWIND': {
        const [effectSymbol, argRegister, contRegister] = operands;
        const effectName = (effectSymbol as Symbol).name;
        const arg = regs[reg(argRegister)];
        const continuation = regs[reg(contRegister)];
        const resumable = continuation instanceof Continuation ? continuation.resumable : true;
        throw new QyEffectSignal(effectName, arg, continuation as Continuation, resumable);
      }
      case 'EFFECT_DISPATCH': {
        const [fnRegister, , argRegister, contRegister] = operands;
        const pending = frame.pendingEffect;
        if (pending === null) {
          throw new QyRuntimeError('EFFECT_DISPATCH reached without a pending effect');
        }
        const [handlerFnIndex, signal] = pending;
        regs[reg(fnRegister)] = new BytecodeFunctionValue(
          this.program.functions[handlerFnIndex],
          frame.env,
          this.program,
        );
        regs[reg(argRegister)] = signal.arg;
        regs[reg(contRegister)] = signal.continuation;
        frame.pendingEffect = null;
        return null;
      }
      case 'CONT_CAPTURE': {
        const [contRegister, , resumeTarget, , dstForResume, multiShot] = operands;
        regs[reg(contRegister)] = this.captureContinuation(frame, {
          resumeTarget: reg(resumeTarget),
          dstForResume: reg(dstForResume),
          resumable: Boolean(multiShot),
        });
        return null;
      }
      case 'CACHE_EVAL': {
        // Python 用 symbol-space 的 KV cache 做 memoization（`_cache_eval`）。
        const [dest, cacheKey, thunkIdx] = operands;
        const key = formatValue(cacheKey);
        if (this.cache.has(key)) {
          regs[reg(dest)] = this.cache.get(key);
          return null;
        }
        const value = await this.runThunk(reg(thunkIdx), frame.env);
        this.cache.set(key, value);
        regs[reg(dest)] = value;
        return null;
      }
      case 'SLOT_COMPLETE': {
        // 对应 `machine.py::SLOT_COMPLETE` + `_slot_symbol`：从程序级 layout 把
        // `BindingAddr(space, slot)` 还原成 Symbol 再 `define_once`。
        // 交换格式自本轮起携带 `symbol_spaces`，因此与 Python 行为一致；
        // 若程序没有 layout（compat 方言），地址无法解析 -> no-op（同 Python 返回 None）。
        const address = instruction.operands[0] as unknown as { space?: number; slot?: number };
        const layout = this.program.symbolSpaces.find((item) => item.id === address?.space);
        const slot = layout?.slots[address?.slot ?? -1];
        if (layout !== undefined && slot !== undefined && slot.symbol.length > 0) {
          const value = frame.registers[reg(instruction.operands[1] as number)];
          frame.env.defineOnce(slot.symbol, value);
        }
        return null;
      }
      default:
        throw new QyRuntimeError(`unsupported opcode '${instruction.opcode}'`);
    }
  }

  // -- 符号解析 -------------------------------------------------------------

  /**
   * LOAD_ENV 的解析。
   *
   * 与 Python 的差异：交换格式会带上 `hygiene_bindings`（宏卫生别名 → 原始名），
   * 而 Python 的 `load_bytecode_json` 丢弃它、导致这类产物无法执行。这里优先用
   * 卫生别名表还原，再退回普通解析。
   */
  private resolveEnv(env: Env, symbol: Symbol): QyValue {
    const target = this.program.hygieneBindings.get(symbol.name);
    if (target !== undefined) {
      try {
        return env.resolve(new Symbol(target));
      } catch (error) {
        if (!(error instanceof QyResolveError)) throw error;
      }
    }
    return env.resolve(symbol);
  }

  // -- 调用 ----------------------------------------------------------------

  /** 调用任意可调用值（对应 `_call`）。 */
  private async call(callee: QyValue, args: QyValue[], env: Env): Promise<QyValue> {
    if (callee instanceof BytecodeFunctionValue) {
      return (await this.runFunction(callee, args)).value;
    }
    if (callee instanceof RawOperatorValue) {
      return await callee.fn(args, env);
    }
    if (callee instanceof PureOperatorValue) {
      try {
        return await callee.fn(...args);
      } catch (error) {
        if (error instanceof EvaluationError) throw error;
        throw new QyRuntimeError(String(error));
      }
    }
    if (typeof callee === 'function') {
      return await (callee as (...values: QyValue[]) => QyValue)(...args);
    }
    throw new QyTypeError(`bytecode call resolved to non-callable ${String(callee)}`);
  }

  // -- effect ---------------------------------------------------------------

  /** `perform`：捕获当前帧并抛 effect signal（对应 `_perform`）。 */
  private async perform(frame: Frame, destReg: number, effectSym: Symbol, arg: QyValue): Promise<QyValue> {
    const effectName = effectSym.name;
    let resumable = true;
    try {
      const def = frame.env.resolve(effectSym);
      resumable = Boolean((def as { resumable?: boolean })?.resumable ?? true);
    } catch {
      resumable = true;
    }

    if (!resumable) {
      throw new QyEffectSignal(effectName, arg, identityContinuation(effectName, false), false);
    }

    const snapshot: EffectFrameSnapshot = {
      registers: frame.registers.slice(),
      env: frame.env,
      pc: frame.pc,
      parents: frame.parents.slice(),
      results: frame.results.slice(),
      functionValue: frame.functionValue,
      fn: frame.fn,
      handlers: frame.handlers.slice(),
    };
    const continuation = new Continuation(effectName, true, (value: QyValue) =>
      this.resumeSnapshot(snapshot, destReg, value),
    );
    throw new QyEffectSignal(effectName, arg, continuation, true);
  }

  /** 从快照恢复执行（对应 `_perform` 内嵌的 `resume`）。 */
  private async resumeSnapshot(
    snapshot: EffectFrameSnapshot,
    destReg: number,
    value: QyValue,
  ): Promise<QyValue> {
    const registers = snapshot.registers.slice();
    registers[destReg] = value;
    let frame: Frame = {
      functionValue: snapshot.functionValue,
      fn: snapshot.fn,
      pc: snapshot.pc,
      registers,
      env: snapshot.env,
      parents: snapshot.parents.slice(),
      results: snapshot.results.slice(),
      handlers: snapshot.handlers.slice(),
      pendingEffect: null,
    };
    while (frame.pc < frame.fn.instructions.length) {
      const instruction = frame.fn.instructions[frame.pc];
      frame.pc += 1;
      const result = await this.executeInstruction(frame, instruction);
      if (result instanceof FrameResult) return result.value;
      if (result !== null) frame = result;
    }
    return null;
  }

  /** `handle`：跑 body，捕获 effect 后分派（对应 `_handle`）。 */
  private async handle(bodyFnIdx: number, handlerSpecs: HandlerSpec[], env: Env): Promise<QyValue> {
    const bodyFn = new BytecodeFunctionValue(this.program.functions[bodyFnIdx], env, this.program);
    try {
      const result = await this.runFunction(bodyFn, []);
      return result.value;
    } catch (error) {
      if (error instanceof QyEffectSignal) {
        return await this.dispatchEffect(error, handlerSpecs, env);
      }
      throw error;
    }
  }

  /** 匹配并执行 handler，并在 handler resume 时保持 handler 活跃。 */
  private async dispatchEffect(
    signal: QyEffectSignal,
    handlerSpecs: HandlerSpec[],
    env: Env,
  ): Promise<QyValue> {
    const findHandler = (effect: string): BytecodeFunctionValue | null => {
      for (const spec of handlerSpecs) {
        if (!Array.isArray(spec) || spec.length !== 2) continue;
        const [effectSym, handlerFnIdx] = spec;
        if (!(effectSym instanceof Symbol) || typeof handlerFnIdx !== 'number') continue;
        if (effectSym.name === effect) {
          return new BytecodeFunctionValue(this.program.functions[handlerFnIdx], env, this.program);
        }
      }
      return null;
    };

    let handlerFn = findHandler(signal.effect);
    if (handlerFn === null) throw signal;

    let arg: QyValue = signal.arg;
    let continuation: QyValue = signal.continuation;
    for (;;) {
      try {
        const handlerResult = await this.runFunction(handlerFn, [arg, continuation]);
        const resultValue = handlerResult.value;
        if (resultValue instanceof Continuation) {
          if (!resultValue.resumable) return resultValue;
          continuation = resultValue;
          arg = null;
        } else {
          return resultValue;
        }
      } catch (nested) {
        if (!(nested instanceof QyEffectSignal)) throw nested;
        const nextHandler = findHandler(nested.effect);
        if (nextHandler === null) throw nested;
        handlerFn = nextHandler;
        arg = nested.arg;
        continuation = nested.continuation;
      }
    }
  }

  /** `resume`（对应 `_resume`）。 */
  private async resume(continuation: QyValue, value: QyValue): Promise<QyValue> {
    if (!(continuation instanceof Continuation)) {
      throw new QyRuntimeError('resume expects a continuation');
    }
    return (await continuation.resume(value)) as QyValue;
  }

  /** 捕获 continuation（`_capture_continuation`，CONT_CAPTURE 路径）。 */
  private captureContinuation(
    frame: Frame,
    options: { resumeTarget: number; dstForResume: number; resumable: boolean },
  ): Continuation {
    const snapshot: EffectFrameSnapshot = {
      registers: frame.registers.slice(),
      env: frame.env,
      pc: options.resumeTarget,
      parents: frame.parents.slice(),
      results: frame.results.slice(),
      functionValue: frame.functionValue,
      fn: frame.fn,
      handlers: frame.handlers.slice(),
    };
    return new Continuation('<continuation>', options.resumable, (value: QyValue) =>
      this.resumeSnapshot(snapshot, options.dstForResume, value),
    );
  }

  /** CALL 时把 signal 交给本帧最近的匹配 handler（`_dispatch_to_handler`）。 */
  private dispatchToHandler(frame: Frame, signal: QyEffectSignal): boolean {
    for (let index = frame.handlers.length - 1; index >= 0; index -= 1) {
      const record = frame.handlers[index];
      for (const spec of record.specs) {
        if (!Array.isArray(spec) || spec.length !== 2) continue;
        const [effectSymbol, handlerFnIndex] = spec as HandlerSpec;
        if (!(effectSymbol instanceof Symbol) || typeof handlerFnIndex !== 'number') continue;
        if (effectSymbol.name === signal.effect) {
          frame.pendingEffect = [handlerFnIndex, signal];
          frame.pc = record.target;
          return true;
        }
      }
    }
    return false;
  }

  // -- 并发形式 --------------------------------------------------------------
  //
  // 语义边界（重要）：
  //
  // Python 用 asyncio 并发执行 thunk；TS 用 Promise.allSettled / Promise.race。
  // 两者只有在 "thunk 不产生可观察副作用" 时才可证明等价，所以这里先做一次
  // 保守的静态纯度判定 `thunksAreConcurrencySafe`：
  //
  //   - 允许：LOAD_HOST / LOAD_ENV / MOVE / MAKE_FUNCTION / BUILD_TUPLE /
  //     JUMP / JUMP_IF_FALSE / RETURN，纯内建的 CALL_BUILTIN，以及 CALL /
  //     TAIL_CALL / APPLY（被调函数由 reachable 集合保守覆盖）；
  //   - 禁止：一切 effect / continuation / handler opcode（PERFORM、HANDLE、
  //     RESUME、RAISE_EFFECT、EFFECT_*、CONT_*、HANDLER_*、SLOT_COMPLETE、
  //     DEFEFFECT）、共享状态写入（STORE_LOCAL、DEFINE_ONCE、DEFINE_MODULE、
  //     FROM_IMPORT、SS_ENTER / SS_LEAVE）、CACHE_EVAL、RUNTIME_EVAL、
  //     嵌套 gather，以及 display / echo / newline / read / read-int 这些有
  //     IO 的内建。
  //
  // `CALL` 的目标无法静态解析，所以把整个程序里所有 MAKE_FUNCTION 目标都算作
  // 可能被调用（保守过近似）。任何一个 reachable 函数不纯，整批 thunk 就退回
  // 顺序执行——此时结果仍然正确，只是没有并发。宿主函数
  // （`registerHostFunction`）经 CALL 调用，被视为宿主声明的纯算子：宿主若在
  // 其中持有共享可变状态，需要自己保证并发安全（见 embed.ts）。

  private async runThunk(index: number, env: Env): Promise<QyValue> {
    const thunk = new BytecodeFunctionValue(this.program.functions[index], env, this.program);
    return (await this.runFunction(thunk, [])).value;
  }

  /** 从 `index` 出发收集 MAKE_FUNCTION 可达的函数下标（局部调用图）。 */
  private collectReachableFunctions(index: number, into: Set<number>): void {
    const stack: number[] = [index];
    while (stack.length > 0) {
      const current = stack.pop() as number;
      if (into.has(current)) continue;
      into.add(current);
      const fn = this.program.functions[current];
      if (fn === undefined) continue;
      for (const instruction of fn.instructions) {
        if (instruction.opcode !== 'MAKE_FUNCTION') continue;
        const target = instruction.operands[1];
        if (typeof target === 'number') stack.push(target);
      }
    }
  }

  /** 单个函数是否只包含并发安全的指令（见上文边界）。 */
  private functionIsConcurrencySafe(fn: BytecodeFunction): boolean {
    for (const instruction of fn.instructions) {
      switch (instruction.opcode) {
        case 'LOAD_HOST':
        case 'LOAD_ENV':
        case 'MOVE':
        case 'MAKE_FUNCTION':
        case 'BUILD_TUPLE':
        case 'JUMP':
        case 'JUMP_IF_FALSE':
        case 'RETURN':
        case 'CALL':
        case 'TAIL_CALL':
        case 'APPLY':
          break;
        case 'CALL_BUILTIN': {
          const builtinId = instruction.operands[1];
          if (typeof builtinId !== 'number' || CONCURRENCY_UNSAFE_BUILTINS.has(builtinId)) {
            return false;
          }
          break;
        }
        default:
          return false;
      }
    }
    for (const instruction of fn.instructions) {
      if (instruction.opcode !== 'LOAD_ENV') continue;
      const symbol = instruction.operands[1];
      if (symbol instanceof Symbol && CONCURRENCY_UNSAFE_SYMBOLS.has(symbol.name)) return false;
    }
    return true;
  }

  /** 整批 thunk 是否可以真正并发（保守判定，见上文边界）。 */
  private thunksAreConcurrencySafe(thunkIndices: number[]): boolean {
    const reachable = new Set<number>();
    for (const index of thunkIndices) this.collectReachableFunctions(index, reachable);
    // 动态 CALL 的保守过近似：任何 MAKE_FUNCTION 目标都可能被调用。
    for (const fn of this.program.functions) {
      for (const instruction of fn.instructions) {
        if (instruction.opcode !== 'MAKE_FUNCTION') continue;
        const target = instruction.operands[1];
        if (typeof target === 'number') reachable.add(target);
      }
    }
    for (const index of reachable) {
      const fn = this.program.functions[index];
      if (fn !== undefined && !this.functionIsConcurrencySafe(fn)) return false;
    }
    return true;
  }

  /**
   * `parallel`（aggregateErrors=true）/ `all`（false）：收集所有 thunk 的结果。
   *
   * 结果顺序与 thunk 声明顺序一致（`Promise.allSettled` 保序，对应
   * `asyncio.gather` 的返回顺序）。错误语义对齐 Python `_parallel_gather`：
   * aggregate 时抛 `QyAggregateError`，否则抛第一个（按声明顺序）错误。
   */
  private async parallelGather(
    thunkIndices: number[],
    env: Env,
    aggregateErrors: boolean,
  ): Promise<QyValue> {
    if (!this.thunksAreConcurrencySafe(thunkIndices)) {
      // 顺序回退：涉及 effect / IO / 共享状态的 thunk 无法安全并发。
      const sequential: QyValue[] = [];
      for (const index of thunkIndices) sequential.push(await this.runThunk(index, env));
      return new TupleValue(sequential);
    }
    const settled = await Promise.allSettled(thunkIndices.map((index) => this.runThunk(index, env)));
    const results: QyValue[] = [];
    const errors: QyError[] = [];
    for (const outcome of settled) {
      if (outcome.status === 'fulfilled') {
        results.push(outcome.value);
      } else {
        results.push(null);
        const reason = outcome.reason;
        errors.push(reason instanceof QyError ? reason : new QyRuntimeError(String(reason)));
      }
    }
    if (errors.length > 0) {
      if (aggregateErrors) {
        throw new QyAggregateError(`parallel failed with ${errors.length} error(s)`, errors);
      }
      throw errors[0];
    }
    return new TupleValue(results);
  }

  /**
   * `race`：第一个完成的 thunk 胜出（对应 Python `_race_first`）。
   *
   * Python 会 cancel 其余 task；JS 无法取消，但输掉的 Promise 已经挂在
   * `Promise.race` 上，不会成为 unhandled rejection。边界：Python 的 asyncio
   * 对"纯同步 thunk"会按调度顺序跑到完成，胜者是下标最小的那个；TS 的 await
   * 逐指令让出，指令更少的 thunk 可能先完成。有真实 async 宿主调用时两者都是
   * "真正最快者胜出"。
   */
  private async raceFirst(thunkIndices: number[], env: Env): Promise<QyValue> {
    if (thunkIndices.length === 0) return null;
    if (!this.thunksAreConcurrencySafe(thunkIndices)) {
      for (const index of thunkIndices) return await this.runThunk(index, env);
      return null;
    }
    return await Promise.race(thunkIndices.map((index) => this.runThunk(index, env)));
  }

  // -- 模块 ------------------------------------------------------------------

  /** `module`：创建模块空间、执行 body、注册模块（`_define_module`）。 */
  private async defineModule(
    moduleName: string,
    functionIndex: number,
    env: Env,
    exportNames: string[],
  ): Promise<QyValue> {
    const moduleEnv = env.child();
    const baseline = new Set(moduleEnv.localBindings().keys());
    const bodyFn = new BytecodeFunctionValue(
      this.program.functions[functionIndex],
      moduleEnv,
      this.program,
    );
    await this.runFunction(bodyFn, []);

    const allBindings = new Map<string, QyValue>();
    for (const [key, value] of moduleEnv.localBindings()) {
      if (!baseline.has(key)) allBindings.set(key, value);
    }

    let selected: Map<string, QyValue>;
    if (exportNames.length > 0) {
      selected = new Map();
      for (const name of exportNames) {
        if (allBindings.has(name)) selected.set(name, allBindings.get(name));
      }
    } else {
      selected = allBindings;
    }

    // 运行期没有 MacroDefinition 值（宏在编译期已展开），因此 runtime_exports
    // 就是全部；再合并注册表里已有的 provisional macro_exports。
    const runtimeExports = new Map(selected);
    let macroExports = new Map<string, QyValue>();
    const provisional = lookupModule(moduleName);
    if (provisional !== undefined) {
      macroExports = new Map(provisional.macroExports);
    }
    const module = new ModuleValue(moduleName, runtimeExports, macroExports);
    registerModule(module);
    return env.defineOnce(moduleName, module);
  }

  /**
   * `from ... import ...`（`_from_import`）。
   *
   * 差异：交换格式不携带模块的 macro_exports，而宏名在运行期本就不会被引用
   * （编译期已内联），所以对"未知名字"选择跳过而不是抛 KeyError。
   */
  private fromImport(moduleName: string, specs: QyValue[], env: Env): void {
    const module = lookupModule(moduleName) ?? builtinModules().get(moduleName);
    if (module === undefined) {
      throw new QyRuntimeError(`cannot load module '${moduleName}'`);
    }
    for (const rawSpec of specs) {
      const spec = rawSpec as { name: string; alias: string };
      if (module.exports.has(spec.name)) {
        env.defineOnce(spec.alias, module.exports.get(spec.name));
      } else if (!module.macroExports.has(spec.name)) {
        // 宏导出的运行期残留：跳过（见上面的说明）。
        continue;
      }
    }
  }

  // -- runtime eval ----------------------------------------------------------
  //
  // RUNTIME_EVAL 携带 chain 的支持子集与限制（对应 `machine.py::_eval_form`）：
  //
  // Python 把 datum 原样送进完整编译管线（core-forms → HIR → MIR → LIR →
  // bytecode），所以 `(eval form)` 对任意 core form 都成立（含 special form、
  // 宏展开、perform/handle、define）。TS 宿主没有编译器，只能提供一个最小的
  // eager 解释器，支持的子集是：
  //
  //   1. `Symbol`：等价于编译后的 `LOAD_ENV`，走 env.resolve（含数字/字符串/
  //      `nil`/`T` 的字面量回退）。语料 41 的 `(eval (reify 42))` 走这条路径。
  //   2. 非 Symbol / 非 Chain 的 datum：原样返回（与 Python `return form` 一致）。
  //   3. `Chain`：
  //      a. `(quote X)` → X（对应编译期的 quote 展开）；
  //      b. 其余按"已解析算子 + eager 求值实参"调用。
  //
  // 明确**不支持**（会 QyResolveError 或得到与 Python 不同的结果）：
  //
  //   - special form / 宏（`define`、`defun`、`lambda`、`cond`、`let`、
  //     `perform`、`handle` 等）；
  //   - 需要编译期环境（宏命名空间、symbol-space layout）的形式；
  //   - `Chain` 里的字面量拼写（Python 管线会解析，eager 解释器只在
  //     Symbol 分支走字面量回退）。
  //
  // 这是宿主能力缺口，不做"第二套语义实现"来补：那会与 compiler 的语义真源
  // 分叉。嵌入方若需要完整 `eval`，应把 form 通过 `qy export` 编译后再进入 VM。

  private async evalForm(form: QyValue, env: Env): Promise<QyValue> {
    if (form instanceof Symbol) return env.resolve(form);
    if (form instanceof Chain) return await this.evalChain(form, env);
    return form;
  }

  private async evalChain(form: Chain, env: Env): Promise<QyValue> {
    const head = form.head;
    const rest = form.tail;
    if (head instanceof Symbol && head.name === 'quote') {
      return rest instanceof Chain ? rest.head : QY_NIL;
    }
    const callee = head instanceof Symbol ? env.resolve(head) : await this.evalForm(head, env);
    const rawArgs = rest instanceof Chain ? chainToArray(rest) : rest === QY_NIL ? [] : [rest];
    const args: QyValue[] = [];
    for (const item of rawArgs) args.push(await this.evalForm(item, env));
    return await this.call(callee, args, env);
  }
}

// ---------------------------------------------------------------------------
// 工具
// ---------------------------------------------------------------------------

function asNumberArray(value: QyValue): number[] {
  if (!Array.isArray(value)) throw new QyTypeError('expected register tuple');
  return value.map((item) => item as number);
}

function chainToArray(value: QyValue): QyValue[] {
  const items: QyValue[] = [];
  let current: QyValue = value;
  while (current instanceof Chain) {
    items.push(current.head);
    current = current.tail;
  }
  return items;
}

/**
 * APPLY 的实参序列归一（`_sequence_to_args`）。
 * 注意字面量拼写（Symbol "1"）会被还原为字面量值 —— 语料 01 依赖它。
 */
export function sequenceToArgs(value: QyValue): QyValue[] {
  if (Array.isArray(value)) return value.map(normalizeArgument);
  if (value === QY_NIL) return [];
  if (value instanceof TupleValue || value instanceof ListValue) {
    return value.items.map(normalizeArgument);
  }
  if (value instanceof Chain) return chainToArray(value).map(normalizeArgument);
  if (value instanceof StringValue) return [normalizeArgument(value)];
  return [normalizeArgument(value)];
}

export { QyError };
