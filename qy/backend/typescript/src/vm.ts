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
// 并发：`parallel` / `all` / `race` 在 Python 里用 asyncio 并发；这里顺序执行，
// 结果顺序与 `asyncio.gather` 一致（语料无副作用，行为等价）。

import { QyEffectSignal, QyError, QyResolveError, QyRuntimeError, QyTypeError, EvaluationError } from './errors.ts';
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
        regs[reg(dest)] = await this.parallelGather(thunks.map((item) => reg(item)), frame.env);
        return null;
      }
      case 'ALL_GATHER': {
        const [dest, ...thunks] = operands;
        regs[reg(dest)] = await this.parallelGather(thunks.map((item) => reg(item)), frame.env);
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

  private async runThunk(index: number, env: Env): Promise<QyValue> {
    const thunk = new BytecodeFunctionValue(this.program.functions[index], env, this.program);
    return (await this.runFunction(thunk, [])).value;
  }

  /** `parallel` / `all`：收集所有 thunk 的结果为 TupleValue。 */
  private async parallelGather(thunkIndices: number[], env: Env): Promise<QyValue> {
    const raw: QyValue[] = [];
    for (const index of thunkIndices) raw.push(await this.runThunk(index, env));
    return new TupleValue(raw);
  }

  /** `race`：顺序执行时取第一个完成者（语料无并发副作用）。 */
  private async raceFirst(thunkIndices: number[], env: Env): Promise<QyValue> {
    for (const index of thunkIndices) return await this.runThunk(index, env);
    return null;
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

  /**
   * `RUNTIME_EVAL`（`_eval_form`）。
   *
   * Python 会把 datum 送进完整编译管线（source → HIR → MIR → LIR → bytecode）。
   * TS VM 里没有编译器，所以：
   *   - Symbol → 直接解析（与编译后 LOAD_ENV 等价）；
   *   - nil/其它非 syntax datum → 原样返回（与 Python 的 `return form` 一致）；
   *   - Chain → 用一个最小的 eager 解释器求值（支持 quote / 已解析算子调用）。
   * 这是宿主能力缺口，已在报告中列为"交换格式/宿主能力"限制。
   */
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
