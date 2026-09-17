package vm

import (
	"fmt"
	"math/big"
	"os"

	"github.com/Cosmic-Developers-Union/Qy/qy/backend/golang/pkg/bytecode"
)

// 寄存器虚拟机：指令分派与语义。
//
// 这是 `qy/vm/instance/machine.py::RegisterVirtualMachine` 的 Go 移植，
// 与 `qy/backend/typescript/src/vm.ts` 逐指令对齐；每条 case 标注对应 Python 位置。
//
// 并发说明：`parallel` / `all` 在 Python 里用 asyncio 并发，这里与 TS 版一样
// 顺序执行；结果顺序与 `asyncio.gather` 一致（语料无副作用，行为等价）。

// BuiltinFunc 是 CALL_BUILTIN 的内建算子实现体（下标见 stdlib 的 ABI 表）。
type BuiltinFunc func(args []Value) (Value, error)

// VM 是一次执行的虚拟机实例。
type VM struct {
	// Program 是装载的字节码程序（JSON 层）。
	Program *bytecode.Program
	// Env 是标准运行环境（symbol-space-chain 的头）。
	Env *Env
	// Builtins 是 CALL_BUILTIN 的下标 ABI 表；由 stdlib 装配。
	Builtins []BuiltinFunc
	// Modules 是模块注册表（当前 VM 实例私有）。
	Modules map[string]*ModuleValue
	// Debug 打开逐指令 trace（写 stderr）。
	Debug bool

	functions []*BytecodeFunction
	cache     map[string]Value
}

// FrameResult 是 `runFunction` 的返回：函数结束时的值 + 收集到的结果列表。
type FrameResult struct {
	Value   Value
	Results []Value
}

// Frame 是执行帧。字段与 Python `_Frame` 一一对应。
type Frame struct {
	FunctionValue *FunctionValue
	Fn            *BytecodeFunction
	PC            int
	Registers     []Value
	Env           *Env
	Parents       []*Env
	Results       []Value
	Handlers      []HandlerRecord
	PendingEffect *PendingEffect
}

// PendingEffect 是 HANDLER_PUSH 路径下待分派的 effect。
type PendingEffect struct {
	HandlerFnIndex int
	Signal         *EffectSignal
}

// effectFrameSnapshot 是 effect 触发时的帧快照（对应 `machine.py::_EffectFrame`）。
type effectFrameSnapshot struct {
	Registers     []Value
	Env           *Env
	PC            int
	Parents       []*Env
	Results       []Value
	FunctionValue *FunctionValue
	Fn            *BytecodeFunction
	Handlers      []HandlerRecord
}

// NewVM 构造虚拟机（对应 `RegisterVirtualMachine.__init__`）。
func NewVM(program *bytecode.Program, env *Env) (*VM, error) {
	if env == nil {
		env = NewEnv(nil)
	}
	functions, err := decodeFunctions(program)
	if err != nil {
		return nil, err
	}
	return &VM{
		Program:   program,
		Env:       env,
		Modules:   map[string]*ModuleValue{},
		functions: functions,
		cache:     map[string]Value{},
	}, nil
}

// Functions 返回解码后的函数表（宿主调试用）。
func (vm *VM) Functions() []*BytecodeFunction { return vm.functions }

// EvaluateProgram 求值整个程序，返回 APPEND_RESULT 收集到的结果列表。
func (vm *VM) EvaluateProgram() ([]Value, error) {
	if vm.Program.Main < 0 || vm.Program.Main >= len(vm.functions) {
		return nil, NewRuntimeError(fmt.Sprintf("program has no function #%d", vm.Program.Main))
	}
	main := &FunctionValue{Fn: vm.functions[vm.Program.Main], Closure: vm.Env}
	result, err := vm.runFunction(main, nil)
	if err != nil {
		if signal, ok := asEffectSignal(err); ok {
			return nil, &UnhandledEffectError{Effect: signal.Effect, Arg: signal.Arg}
		}
		return nil, err
	}
	return result.Results, nil
}

// Evaluate 求值并返回最后一个结果（对应 Python `evaluate`）。
func (vm *VM) Evaluate() (Value, error) {
	results, err := vm.EvaluateProgram()
	if err != nil {
		return nil, err
	}
	if len(results) == 0 {
		return nil, nil
	}
	return results[len(results)-1], nil
}

// runFunction 执行一个函数体（对应 `_run_function`）。
func (vm *VM) runFunction(functionValue *FunctionValue, args []Value) (*FrameResult, error) {
	frame, err := vm.makeFrame(functionValue, args)
	if err != nil {
		return nil, err
	}
	for {
		if frame.PC >= len(frame.Fn.Instructions) {
			// 指令耗尽（Python 会 IndexError；正常 emit 不会出现）
			return &FrameResult{Value: nil, Results: frame.Results}, nil
		}
		instruction := &frame.Fn.Instructions[frame.PC]
		frame.PC++
		if vm.Debug {
			fmt.Fprintf(os.Stderr, "  [%s] pc=%d op=%s\n", frame.Fn.Name, frame.PC-1, instruction.Opcode)
		}
		next, result, err := vm.executeInstruction(frame, instruction)
		if err != nil {
			return nil, err
		}
		if result != nil {
			return result, nil
		}
		if next != nil {
			frame = next
		}
	}
}

// makeFrame 创建执行帧（对应 `_make_frame`）。
func (vm *VM) makeFrame(functionValue *FunctionValue, args []Value) (*Frame, error) {
	fn := functionValue.Fn
	if len(args) != len(fn.Params) {
		return nil, NewArityError(fmt.Sprintf(
			"%s expects %d arguments, got %d", fn.Name, len(fn.Params), len(args)))
	}
	var env *Env
	if fn.Name == "<main>" || fn.Name == "<module-body>" {
		env = functionValue.Closure
	} else {
		bindings := make(map[string]Value, len(fn.Params))
		for index, param := range fn.Params {
			bindings[param] = args[index]
		}
		env = functionValue.Closure.ChildWith(bindings)
	}
	return &Frame{
		FunctionValue: functionValue,
		Fn:            fn,
		PC:            0,
		Registers:     make([]Value, fn.RegisterCount),
		Env:           env,
		Parents:       nil,
		Results:       nil,
		Handlers:      nil,
	}, nil
}

// put 写入寄存器（越界时报错而不是 panic）。
func (f *Frame) put(index int, value Value) error {
	if index < 0 || index >= len(f.Registers) {
		return NewRuntimeError(fmt.Sprintf(
			"register index %d out of range (register_count=%d) in %s",
			index, len(f.Registers), f.Fn.Name))
	}
	f.Registers[index] = value
	return nil
}

// read 读取寄存器（越界时报错而不是 panic）。
func (f *Frame) read(index int) (Value, error) {
	if index < 0 || index >= len(f.Registers) {
		return nil, NewRuntimeError(fmt.Sprintf(
			"register index %d out of range (register_count=%d) in %s",
			index, len(f.Registers), f.Fn.Name))
	}
	return f.Registers[index], nil
}

// executeInstruction 单条指令分派（对应 `_execute_instruction`）。
//
// 返回 (nextFrame, frameResult, error)：
//   - nextFrame 非 nil 表示尾调用换帧；
//   - frameResult 非 nil 表示函数返回；
//   - 两者都为 nil 表示继续执行下一条指令。
func (vm *VM) executeInstruction(frame *Frame, instruction *Instruction) (*Frame, *FrameResult, error) {
	ops := instruction.Operands
	failure := func(err error) (*Frame, *FrameResult, error) { return nil, nil, err }

	switch instruction.Opcode {
	case bytecode.OpLoadHost:
		if err := frame.put(regOf(ops[0]), ops[1]); err != nil {
			return failure(err)
		}
		return nil, nil, nil

	case bytecode.OpLoadEnv:
		dest := regOf(ops[0])
		value, err := vm.resolveEnv(frame.Env, symbolOf(ops[1]))
		if err != nil {
			return failure(err)
		}
		if err := frame.put(dest, value); err != nil {
			return failure(err)
		}
		return nil, nil, nil

	case bytecode.OpMove:
		value, err := frame.read(regOf(ops[1]))
		if err != nil {
			return failure(err)
		}
		if err := frame.put(regOf(ops[0]), value); err != nil {
			return failure(err)
		}
		return nil, nil, nil

	case bytecode.OpStoreLocal:
		name := symbolOf(ops[0]).Name
		value, err := frame.read(regOf(ops[1]))
		if err != nil {
			return failure(err)
		}
		if !IsCompileTimeMacro(value) {
			frame.Env.Define(name, value)
		}
		return nil, nil, nil

	case bytecode.OpDefineOnce:
		name := symbolOf(ops[0]).Name
		value, err := frame.read(regOf(ops[1]))
		if err != nil {
			return failure(err)
		}
		if !IsCompileTimeMacro(value) {
			if _, err := frame.Env.DefineOnce(name, value); err != nil {
				return failure(err)
			}
		}
		return nil, nil, nil

	case bytecode.OpMakeFunction:
		index := intOf(ops[1])
		if index < 0 || index >= len(vm.functions) {
			return failure(NewRuntimeError(fmt.Sprintf("MAKE_FUNCTION: no function #%d", index)))
		}
		if err := frame.put(regOf(ops[0]), &FunctionValue{Fn: vm.functions[index], Closure: frame.Env}); err != nil {
			return failure(err)
		}
		return nil, nil, nil

	case bytecode.OpMakeMacro:
		if err := frame.put(regOf(ops[0]), CompileTimeMacro); err != nil {
			return failure(err)
		}
		return nil, nil, nil

	case bytecode.OpEnterScope, bytecode.OpSsEnter:
		frame.Parents = append(frame.Parents, frame.Env)
		frame.Env = frame.Env.Child()
		return nil, nil, nil

	case bytecode.OpExitScope, bytecode.OpSsLeave:
		if len(frame.Parents) > 0 {
			frame.Env = frame.Parents[len(frame.Parents)-1]
			frame.Parents = frame.Parents[:len(frame.Parents)-1]
		}
		return nil, nil, nil

	case bytecode.OpAppendResult:
		value, err := frame.read(regOf(ops[0]))
		if err != nil {
			return failure(err)
		}
		if IsCompileTimeMacro(value) {
			value = nil
		}
		frame.Results = append(frame.Results, value)
		return nil, nil, nil

	case bytecode.OpBuildTuple:
		values := make([]Value, 0, len(ops)-1)
		for i := 1; i < len(ops); i++ {
			value, err := frame.read(regOf(ops[i]))
			if err != nil {
				return failure(err)
			}
			values = append(values, value)
		}
		if err := frame.put(regOf(ops[0]), values); err != nil {
			return failure(err)
		}
		return nil, nil, nil

	case bytecode.OpApply:
		dest := regOf(ops[0])
		callee, err := frame.read(regOf(ops[1]))
		if err != nil {
			return failure(err)
		}
		argsValue, err := frame.read(regOf(ops[2]))
		if err != nil {
			return failure(err)
		}
		value, err := vm.call(callee, sequenceToArgs(argsValue), frame.Env)
		if err != nil {
			return failure(err)
		}
		if err := frame.put(dest, value); err != nil {
			return failure(err)
		}
		return nil, nil, nil

	case bytecode.OpRuntimeEval:
		dest := regOf(ops[0])
		form, err := frame.read(regOf(ops[1]))
		if err != nil {
			return failure(err)
		}
		value, err := vm.evalForm(form, frame.Env)
		if err != nil {
			return failure(err)
		}
		if err := frame.put(dest, value); err != nil {
			return failure(err)
		}
		return nil, nil, nil

	case bytecode.OpParallelGather, bytecode.OpAllGather:
		dest := regOf(ops[0])
		indices := make([]int, 0, len(ops)-1)
		for i := 1; i < len(ops); i++ {
			indices = append(indices, intOf(ops[i]))
		}
		value, err := vm.parallelGather(indices, frame.Env)
		if err != nil {
			return failure(err)
		}
		if err := frame.put(dest, value); err != nil {
			return failure(err)
		}
		return nil, nil, nil

	case bytecode.OpRaceFirst:
		dest := regOf(ops[0])
		indices := make([]int, 0, len(ops)-1)
		for i := 1; i < len(ops); i++ {
			indices = append(indices, intOf(ops[i]))
		}
		value, err := vm.raceFirst(indices, frame.Env)
		if err != nil {
			return failure(err)
		}
		if err := frame.put(dest, value); err != nil {
			return failure(err)
		}
		return nil, nil, nil

	case bytecode.OpDefineModule:
		dest := regOf(ops[0])
		moduleName := symbolOf(ops[1]).Name
		exportNames := symbolNamesOf(ops[3])
		value, err := vm.defineModule(moduleName, intOf(ops[2]), exportNames, frame.Env)
		if err != nil {
			return failure(err)
		}
		if err := frame.put(dest, value); err != nil {
			return failure(err)
		}
		return nil, nil, nil

	case bytecode.OpFromImport:
		moduleName := symbolOf(ops[0]).Name
		if err := vm.fromImport(moduleName, importSpecsOf(ops[1]), frame.Env); err != nil {
			return failure(err)
		}
		return nil, nil, nil

	case bytecode.OpDefeffect:
		name := symbolOf(ops[0]).Name
		resumable := true
		if len(ops) > 1 {
			resumable = boolOf(ops[1])
		}
		frame.Env.Define(name, &EffectDefinition{Name: name, Resumable: resumable})
		return nil, nil, nil

	case bytecode.OpPerform:
		dest := regOf(ops[0])
		effectSym := symbolOf(ops[1])
		arg, err := frame.read(regOf(ops[2]))
		if err != nil {
			return failure(err)
		}
		if err := vm.perform(frame, dest, effectSym, arg); err != nil {
			return failure(err)
		}
		return nil, nil, nil

	case bytecode.OpHandle:
		dest := regOf(ops[0])
		value, err := vm.handle(intOf(ops[1]), handlerSpecsOf(ops[2]), frame.Env)
		if err != nil {
			return failure(err)
		}
		if err := frame.put(dest, value); err != nil {
			return failure(err)
		}
		return nil, nil, nil

	case bytecode.OpResume:
		dest := regOf(ops[0])
		continuation, err := frame.read(regOf(ops[1]))
		if err != nil {
			return failure(err)
		}
		value, err := frame.read(regOf(ops[2]))
		if err != nil {
			return failure(err)
		}
		resumed, err := vm.resume(continuation, value)
		if err != nil {
			return failure(err)
		}
		if err := frame.put(dest, resumed); err != nil {
			return failure(err)
		}
		return nil, nil, nil

	case bytecode.OpContRestore:
		continuation, err := frame.read(regOf(ops[0]))
		if err != nil {
			return failure(err)
		}
		value, err := frame.read(regOf(ops[2]))
		if err != nil {
			return failure(err)
		}
		resumed, err := vm.resume(continuation, value)
		if err != nil {
			return failure(err)
		}
		if err := frame.put(regOf(ops[1]), resumed); err != nil {
			return failure(err)
		}
		return nil, nil, nil

	case bytecode.OpContCopy:
		value, err := frame.read(regOf(ops[1]))
		if err != nil {
			return failure(err)
		}
		if err := frame.put(regOf(ops[0]), value); err != nil {
			return failure(err)
		}
		return nil, nil, nil

	case bytecode.OpJump:
		frame.PC = intOf(ops[0])
		return nil, nil, nil

	case bytecode.OpJumpIfFalse:
		value, err := frame.read(regOf(ops[0]))
		if err != nil {
			return failure(err)
		}
		if !CoreTruthy(value) {
			frame.PC = intOf(ops[1])
		}
		return nil, nil, nil

	case bytecode.OpCallBuiltin:
		dest := regOf(ops[0])
		builtinID := intOf(ops[1])
		argRegisters := regTupleOf(ops[2])
		args := make([]Value, 0, len(argRegisters))
		for _, index := range argRegisters {
			value, err := frame.read(index)
			if err != nil {
				return failure(err)
			}
			args = append(args, value)
		}
		if builtinID < 0 || builtinID >= len(vm.Builtins) || vm.Builtins[builtinID] == nil {
			return failure(NewRuntimeError(fmt.Sprintf("unknown builtin operator index %d", builtinID)))
		}
		value, err := vm.Builtins[builtinID](args)
		if err != nil {
			return failure(err)
		}
		if err := frame.put(dest, value); err != nil {
			return failure(err)
		}
		return nil, nil, nil

	case bytecode.OpCall:
		dest := regOf(ops[0])
		callee, err := frame.read(regOf(ops[1]))
		if err != nil {
			return failure(err)
		}
		argRegisters := regTupleOf(ops[2])
		args := make([]Value, 0, len(argRegisters))
		for _, index := range argRegisters {
			value, err := frame.read(index)
			if err != nil {
				return failure(err)
			}
			args = append(args, value)
		}
		value, err := vm.call(callee, args, frame.Env)
		if err != nil {
			if signal, ok := asEffectSignal(err); ok && vm.dispatchToHandler(frame, signal) {
				return nil, nil, nil
			}
			return failure(err)
		}
		if err := frame.put(dest, value); err != nil {
			return failure(err)
		}
		return nil, nil, nil

	case bytecode.OpTailCall:
		callee, err := frame.read(regOf(ops[0]))
		if err != nil {
			return failure(err)
		}
		argRegisters := regTupleOf(ops[1])
		args := make([]Value, 0, len(argRegisters))
		for _, index := range argRegisters {
			value, err := frame.read(index)
			if err != nil {
				return failure(err)
			}
			args = append(args, value)
		}
		if fn, ok := callee.(*FunctionValue); ok {
			next, err := vm.makeFrame(fn, args)
			if err != nil {
				return failure(err)
			}
			return next, nil, nil
		}
		value, err := vm.call(callee, args, frame.Env)
		if err != nil {
			return failure(err)
		}
		return nil, &FrameResult{Value: value, Results: frame.Results}, nil

	case bytecode.OpReturn:
		value, err := frame.read(regOf(ops[0]))
		if err != nil {
			return failure(err)
		}
		if IsCompileTimeMacro(value) {
			value = nil
		}
		return nil, &FrameResult{Value: value, Results: frame.Results}, nil

	case bytecode.OpRaiseEffect:
		effectName := symbolOf(ops[0]).Name
		payload, err := frame.read(regOf(ops[1]))
		if err != nil {
			return failure(err)
		}
		resumable := false
		if len(ops) > 2 {
			resumable = boolOf(ops[2])
		}
		return failure(&EffectSignal{
			Effect:       effectName,
			Arg:          payload,
			Continuation: IdentityContinuation(effectName, resumable),
			Resumable:    resumable,
		})

	case bytecode.OpHandlerPush:
		record := HandlerRecord{
			HandlerID: intOf(ops[0]),
			Target:    intOf(ops[1]),
			Specs:     handlerSpecsOf(ops[3]),
		}
		if ops[2] != nil {
			parentID := intOf(ops[2])
			record.ParentID = &parentID
		}
		frame.Handlers = append(frame.Handlers, record)
		return nil, nil, nil

	case bytecode.OpHandlerPop:
		if len(frame.Handlers) > 0 {
			frame.Handlers = frame.Handlers[:len(frame.Handlers)-1]
		}
		return nil, nil, nil

	case bytecode.OpEffectUnwind:
		effectName := symbolOf(ops[0]).Name
		arg, err := frame.read(regOf(ops[1]))
		if err != nil {
			return failure(err)
		}
		continuation, err := frame.read(regOf(ops[2]))
		if err != nil {
			return failure(err)
		}
		cont, ok := continuation.(*Continuation)
		if !ok {
			return failure(NewTypeError("EFFECT_UNWIND expects a continuation"))
		}
		return failure(&EffectSignal{
			Effect:       effectName,
			Arg:          arg,
			Continuation: cont,
			Resumable:    cont.Resumable,
		})

	case bytecode.OpEffectDispatch:
		if frame.PendingEffect == nil {
			return failure(NewRuntimeError("EFFECT_DISPATCH reached without a pending effect"))
		}
		pending := frame.PendingEffect
		handler := &FunctionValue{Fn: vm.functions[pending.HandlerFnIndex], Closure: frame.Env}
		if err := frame.put(regOf(ops[0]), handler); err != nil {
			return failure(err)
		}
		if err := frame.put(regOf(ops[2]), pending.Signal.Arg); err != nil {
			return failure(err)
		}
		if err := frame.put(regOf(ops[3]), pending.Signal.Continuation); err != nil {
			return failure(err)
		}
		frame.PendingEffect = nil
		return nil, nil, nil

	case bytecode.OpContCapture:
		continuation := vm.captureContinuation(frame, intOf(ops[2]), intOf(ops[4]), boolOf(ops[5]))
		if err := frame.put(regOf(ops[0]), continuation); err != nil {
			return failure(err)
		}
		return nil, nil, nil

	case bytecode.OpCacheEval:
		dest := regOf(ops[0])
		key := FormatValue(ops[1])
		if value, ok := vm.cache[key]; ok {
			if err := frame.put(dest, value); err != nil {
				return failure(err)
			}
			return nil, nil, nil
		}
		value, err := vm.runThunk(intOf(ops[2]), frame.Env)
		if err != nil {
			return failure(err)
		}
		vm.cache[key] = value
		if err := frame.put(dest, value); err != nil {
			return failure(err)
		}
		return nil, nil, nil

	case bytecode.OpSlotComplete:
		// 对应 `machine.py::SLOT_COMPLETE` + `_slot_symbol`：从程序级 layout 把
		// `BindingAddr(space, slot)` 还原成 Symbol 再 `define_once`。
		// compat 方言没有 layout，地址无法解析（Python 返回 None）→ no-op。
		address, ok := ops[0].(bytecode.BindingAddr)
		if !ok {
			return nil, nil, nil
		}
		value, err := frame.read(regOf(ops[1]))
		if err != nil {
			return failure(err)
		}
		if IsCompileTimeMacro(value) {
			return nil, nil, nil
		}
		if symbol := vm.slotSymbol(address); symbol != nil {
			if _, err := frame.Env.DefineOnce(symbol.Name, value); err != nil {
				return failure(err)
			}
		}
		return nil, nil, nil
	}

	return failure(NewRuntimeError("unsupported opcode '" + instruction.Opcode + "'"))
}

// slotSymbol 从程序级 symbol-space layout 还原 `SLOT_COMPLETE` 的绑定符号
// （对应 `machine.py::_slot_symbol`：按 layout.id == space、slots[slot] 定位）。
func (vm *VM) slotSymbol(address bytecode.BindingAddr) *Symbol {
	for _, layout := range vm.Program.SymbolSpaces {
		if layout.ID != address.Space {
			continue
		}
		if address.Slot < 0 || address.Slot >= len(layout.Slots) {
			continue
		}
		slot := layout.Slots[address.Slot]
		if slot.Symbol != "" {
			return NewSymbol(slot.Symbol)
		}
	}
	return nil
}

// ---------------------------------------------------------------------------
// 符号解析
// ---------------------------------------------------------------------------

// resolveEnv 是 LOAD_ENV 的解析。
//
// 交换格式携带 `hygiene_bindings`（宏卫生别名 → 原始名），Python 的
// `_install_hygiene_aliases` 把它装成惰性别名。这里在解析时直接按别名表改解析
// 目标名，再退回普通解析（与 TS 版一致）。
func (vm *VM) resolveEnv(env *Env, symbol *Symbol) (Value, error) {
	if target, ok := vm.Program.HygieneBindings[symbol.Name]; ok {
		if value, err := env.Resolve(NewSymbol(target)); err == nil {
			return value, nil
		}
	}
	return env.Resolve(symbol)
}

// ---------------------------------------------------------------------------
// 调用
// ---------------------------------------------------------------------------

// call 调用任意可调用值（对应 `_call`）。
func (vm *VM) call(callee Value, args []Value, env *Env) (Value, error) {
	switch c := callee.(type) {
	case *FunctionValue:
		result, err := vm.runFunction(c, args)
		if err != nil {
			return nil, err
		}
		return result.Value, nil
	case *RawOperator:
		return c.Fn(args, env)
	case *PureOperator:
		return c.Fn(args)
	case nil:
		return nil, NewTypeError("bytecode call resolved to non-callable none")
	}
	return nil, NewTypeError("bytecode call resolved to non-callable " + Describe(callee))
}

// ---------------------------------------------------------------------------
// effect
// ---------------------------------------------------------------------------

// perform 捕获当前帧并抛 effect signal（对应 `_perform`）。
func (vm *VM) perform(frame *Frame, destReg int, effectSym *Symbol, arg Value) error {
	effectName := effectSym.Name
	resumable := true
	if def, err := frame.Env.Resolve(effectSym); err == nil {
		if definition, ok := def.(*EffectDefinition); ok {
			resumable = definition.Resumable
		}
	}

	if !resumable {
		return &EffectSignal{
			Effect:       effectName,
			Arg:          arg,
			Continuation: IdentityContinuation(effectName, false),
			Resumable:    false,
		}
	}

	snapshot := vm.captureSnapshot(frame, destReg, frame.PC)
	continuation := &Continuation{
		Effect:    effectName,
		Resumable: true,
		ResumeFn: func(value Value) (Value, error) {
			return vm.resumeSnapshot(snapshot, destReg, value)
		},
	}
	return &EffectSignal{
		Effect:       effectName,
		Arg:          arg,
		Continuation: continuation,
		Resumable:    true,
	}
}

// captureSnapshot 深拷贝帧快照（effect 捕获用）。
func (vm *VM) captureSnapshot(frame *Frame, destReg, pc int) *effectFrameSnapshot {
	registers := make([]Value, len(frame.Registers))
	copy(registers, frame.Registers)
	parents := make([]*Env, len(frame.Parents))
	copy(parents, frame.Parents)
	results := make([]Value, len(frame.Results))
	copy(results, frame.Results)
	handlers := make([]HandlerRecord, len(frame.Handlers))
	copy(handlers, frame.Handlers)
	return &effectFrameSnapshot{
		Registers:     registers,
		Env:           frame.Env,
		PC:            pc,
		Parents:       parents,
		Results:       results,
		FunctionValue: frame.FunctionValue,
		Fn:            frame.Fn,
		Handlers:      handlers,
	}
}

// resumeSnapshot 从快照恢复执行（对应 `_perform` 内嵌的 `resume`）。
func (vm *VM) resumeSnapshot(snapshot *effectFrameSnapshot, destReg int, value Value) (Value, error) {
	registers := make([]Value, len(snapshot.Registers))
	copy(registers, snapshot.Registers)
	if destReg < 0 || destReg >= len(registers) {
		return nil, NewRuntimeError(fmt.Sprintf("continuation destination register %d out of range", destReg))
	}
	registers[destReg] = value
	parents := make([]*Env, len(snapshot.Parents))
	copy(parents, snapshot.Parents)
	results := make([]Value, len(snapshot.Results))
	copy(results, snapshot.Results)
	handlers := make([]HandlerRecord, len(snapshot.Handlers))
	copy(handlers, snapshot.Handlers)

	frame := &Frame{
		FunctionValue: snapshot.FunctionValue,
		Fn:            snapshot.Fn,
		PC:            snapshot.PC,
		Registers:     registers,
		Env:           snapshot.Env,
		Parents:       parents,
		Results:       results,
		Handlers:      handlers,
	}
	for frame.PC < len(frame.Fn.Instructions) {
		instruction := &frame.Fn.Instructions[frame.PC]
		frame.PC++
		next, result, err := vm.executeInstruction(frame, instruction)
		if err != nil {
			return nil, err
		}
		if result != nil {
			return result.Value, nil
		}
		if next != nil {
			frame = next
		}
	}
	return nil, nil
}

// handle 跑 body，捕获 effect 后分派（对应 `_handle`）。
func (vm *VM) handle(bodyFnIdx int, specs []HandlerSpec, env *Env) (Value, error) {
	if bodyFnIdx < 0 || bodyFnIdx >= len(vm.functions) {
		return nil, NewRuntimeError(fmt.Sprintf("HANDLE: no function #%d", bodyFnIdx))
	}
	bodyFn := &FunctionValue{Fn: vm.functions[bodyFnIdx], Closure: env}
	result, err := vm.runFunction(bodyFn, nil)
	if err != nil {
		if signal, ok := asEffectSignal(err); ok {
			return vm.dispatchEffect(signal, specs, env)
		}
		return nil, err
	}
	return result.Value, nil
}

// dispatchEffect 匹配并执行 handler，并在 handler resume 时保持 handler 活跃。
func (vm *VM) dispatchEffect(signal *EffectSignal, specs []HandlerSpec, env *Env) (Value, error) {
	findHandler := func(effect string) *FunctionValue {
		for _, spec := range specs {
			if spec.Effect == effect {
				if spec.HandlerFn < 0 || spec.HandlerFn >= len(vm.functions) {
					return nil
				}
				return &FunctionValue{Fn: vm.functions[spec.HandlerFn], Closure: env}
			}
		}
		return nil
	}

	handlerFn := findHandler(signal.Effect)
	if handlerFn == nil {
		return nil, signal
	}

	arg := signal.Arg
	var continuation Value = signal.Continuation
	for {
		result, err := vm.runFunction(handlerFn, []Value{arg, continuation})
		if err != nil {
			nested, ok := asEffectSignal(err)
			if !ok {
				return nil, err
			}
			nextHandler := findHandler(nested.Effect)
			if nextHandler == nil {
				return nil, nested
			}
			handlerFn = nextHandler
			arg = nested.Arg
			continuation = nested.Continuation
			continue
		}
		if cont, ok := result.Value.(*Continuation); ok {
			if !cont.Resumable {
				return cont, nil
			}
			continuation = cont
			arg = nil
			continue
		}
		return result.Value, nil
	}
}

// resume 调用 continuation（对应 `_resume`）。
func (vm *VM) resume(continuation Value, value Value) (Value, error) {
	cont, ok := continuation.(*Continuation)
	if !ok {
		return nil, NewRuntimeError("resume expects a continuation")
	}
	if cont.ResumeFn == nil {
		return nil, NewRuntimeError("continuation has no resume entry")
	}
	return cont.ResumeFn(value)
}

// captureContinuation 捕获 continuation（`_capture_continuation`，CONT_CAPTURE 路径）。
func (vm *VM) captureContinuation(frame *Frame, resumeTarget, dstForResume int, resumable bool) *Continuation {
	snapshot := vm.captureSnapshot(frame, dstForResume, resumeTarget)
	return &Continuation{
		Effect:    "<continuation>",
		Resumable: resumable,
		ResumeFn: func(value Value) (Value, error) {
			return vm.resumeSnapshot(snapshot, dstForResume, value)
		},
	}
}

// dispatchToHandler 把 CALL 时的 signal 交给本帧最近的匹配 handler（`_dispatch_to_handler`）。
func (vm *VM) dispatchToHandler(frame *Frame, signal *EffectSignal) bool {
	for index := len(frame.Handlers) - 1; index >= 0; index-- {
		record := frame.Handlers[index]
		for _, spec := range record.Specs {
			if spec.Effect == signal.Effect {
				frame.PendingEffect = &PendingEffect{HandlerFnIndex: spec.HandlerFn, Signal: signal}
				frame.PC = record.Target
				return true
			}
		}
	}
	return false
}

// ---------------------------------------------------------------------------
// 并发形式
// ---------------------------------------------------------------------------

// runThunk 执行一个 thunk 函数下标。
func (vm *VM) runThunk(index int, env *Env) (Value, error) {
	if index < 0 || index >= len(vm.functions) {
		return nil, NewRuntimeError(fmt.Sprintf("thunk function index %d out of range", index))
	}
	thunk := &FunctionValue{Fn: vm.functions[index], Closure: env}
	result, err := vm.runFunction(thunk, nil)
	if err != nil {
		return nil, err
	}
	return result.Value, nil
}

// parallelGather 收集所有 thunk 的结果为 TupleValue（`parallel` / `all`）。
func (vm *VM) parallelGather(thunkIndices []int, env *Env) (Value, error) {
	items := make([]Value, 0, len(thunkIndices))
	for _, index := range thunkIndices {
		value, err := vm.runThunk(index, env)
		if err != nil {
			return nil, err
		}
		items = append(items, value)
	}
	return NewTuple(items), nil
}

// raceFirst 取第一个 thunk 的结果（`race`）。
//
// 与 TS 版一致：顺序执行时取第一个 thunk；Python 版用 asyncio 取最先完成者。
// 语料中所有 thunk 都成功且无副作用，行为等价；真正并发的抢跑语义未实现（见报告）。
func (vm *VM) raceFirst(thunkIndices []int, env *Env) (Value, error) {
	if len(thunkIndices) == 0 {
		return nil, nil
	}
	return vm.runThunk(thunkIndices[0], env)
}

// ---------------------------------------------------------------------------
// 模块
// ---------------------------------------------------------------------------

// defineModule 创建模块空间、执行 body、注册模块（`_define_module`）。
func (vm *VM) defineModule(moduleName string, functionIndex int, exportNames []string, env *Env) (Value, error) {
	if functionIndex < 0 || functionIndex >= len(vm.functions) {
		return nil, NewRuntimeError(fmt.Sprintf("DEFINE_MODULE: no function #%d", functionIndex))
	}
	moduleEnv := env.Child()
	baseline := map[string]bool{}
	for name := range moduleEnv.LocalBindings() {
		baseline[name] = true
	}
	bodyFn := &FunctionValue{Fn: vm.functions[functionIndex], Closure: moduleEnv}
	if _, err := vm.runFunction(bodyFn, nil); err != nil {
		return nil, err
	}

	allBindings := map[string]Value{}
	for name, value := range moduleEnv.LocalBindings() {
		if !baseline[name] {
			allBindings[name] = value
		}
	}

	selected := allBindings
	if len(exportNames) > 0 {
		selected = map[string]Value{}
		for _, name := range exportNames {
			if value, ok := allBindings[name]; ok {
				selected[name] = value
			}
		}
	}

	// 运行期没有 MacroDefinition 值（宏在编译期已展开），因此 runtime_exports
	// 就是全部；再合并注册表里已有的 provisional macro_exports。
	runtimeExports := make(map[string]Value, len(selected))
	for name, value := range selected {
		runtimeExports[name] = value
	}
	macroExports := map[string]Value{}
	if provisional, ok := vm.Modules[moduleName]; ok {
		for name, value := range provisional.MacroExports {
			macroExports[name] = value
		}
	}
	module := &ModuleValue{Name: moduleName, Exports: runtimeExports, MacroExports: macroExports}
	vm.Modules[moduleName] = module
	return env.DefineOnce(moduleName, module)
}

// fromImport 处理 `from ... import ...`（`_from_import`）。
//
// 编译期宏导出（`module_macro_exports`）在运行期没有绑定值：命中时跳过绑定，
// 而不是报「模块没有该导出」。
func (vm *VM) fromImport(moduleName string, specs []ImportSpec, env *Env) error {
	module, ok := vm.Modules[moduleName]
	if !ok {
		return NewRuntimeError("cannot load module '" + moduleName + "'")
	}
	for _, spec := range specs {
		if value, exists := module.Exports[spec.Name]; exists {
			if _, err := env.DefineOnce(spec.Alias, value); err != nil {
				return err
			}
			continue
		}
		if _, exists := module.MacroExports[spec.Name]; exists {
			continue
		}
		if vm.isCompileTimeMacroExport(moduleName, spec.Name) {
			continue
		}
		return NewRuntimeError("module '" + moduleName + "' has no export '" + spec.Name + "'")
	}
	return nil
}

// isCompileTimeMacroExport 判断导出是否是编译期宏导出
// （字节码交换格式携带的 `module_macro_exports`，对应 `_is_compile_time_macro_export`）。
func (vm *VM) isCompileTimeMacroExport(moduleName, name string) bool {
	for _, candidate := range vm.Program.ModuleMacroExports[moduleName] {
		if candidate == name {
			return true
		}
	}
	return false
}

// ---------------------------------------------------------------------------
// runtime eval
// ---------------------------------------------------------------------------

// evalForm 是 `RUNTIME_EVAL`（`_eval_form`）。
//
// Python 会把 datum 送进完整编译管线；Go VM 里没有编译器，所以：
//   - Symbol → 直接解析（与编译后 LOAD_ENV 等价）；
//   - nil / 其它非 syntax datum → 原样返回（与 Python 的 `return form` 一致）；
//   - Chain → 用一个最小的 eager 解释器求值（支持 quote / 已解析算子调用）。
func (vm *VM) evalForm(form Value, env *Env) (Value, error) {
	switch f := form.(type) {
	case *Symbol:
		return env.Resolve(f)
	case *Chain:
		return vm.evalChain(f, env)
	}
	return form, nil
}

func (vm *VM) evalChain(form *Chain, env *Env) (Value, error) {
	head := form.Head
	rest := form.Tail
	if symbol, ok := head.(*Symbol); ok && symbol.Name == "quote" {
		if chain, ok := rest.(*Chain); ok {
			return chain.Head, nil
		}
		return QyNil, nil
	}
	var callee Value
	if symbol, ok := head.(*Symbol); ok {
		resolved, err := env.Resolve(symbol)
		if err != nil {
			return nil, err
		}
		callee = resolved
	} else {
		resolved, err := vm.evalForm(head, env)
		if err != nil {
			return nil, err
		}
		callee = resolved
	}
	rawArgs := ChainValueToSlice(rest)
	args := make([]Value, 0, len(rawArgs))
	for _, item := range rawArgs {
		value, err := vm.evalForm(item, env)
		if err != nil {
			return nil, err
		}
		args = append(args, value)
	}
	return vm.call(callee, args, env)
}

// ---------------------------------------------------------------------------
// 操作数工具
// ---------------------------------------------------------------------------

func regOf(value Value) int {
	if n, ok := value.(int); ok {
		return n
	}
	if integer, ok := value.(*big.Int); ok && integer.IsInt64() {
		return int(integer.Int64())
	}
	return 0
}

func intOf(value Value) int {
	switch v := value.(type) {
	case int:
		return v
	case float64:
		return int(v)
	case *big.Int:
		if v.IsInt64() {
			return int(v.Int64())
		}
	}
	return 0
}

func boolOf(value Value) bool {
	if b, ok := value.(bool); ok {
		return b
	}
	return false
}

func symbolOf(value Value) *Symbol {
	if symbol, ok := value.(*Symbol); ok {
		return symbol
	}
	return NewSymbol("")
}

func symbolNamesOf(value Value) []string {
	symbols, ok := value.([]*Symbol)
	if !ok {
		return nil
	}
	names := make([]string, 0, len(symbols))
	for _, symbol := range symbols {
		names = append(names, symbol.Name)
	}
	return names
}

func handlerSpecsOf(value Value) []HandlerSpec {
	switch specs := value.(type) {
	case []HandlerSpec:
		return specs
	case []Value:
		// abstract-machine 方言：HANDLER_PUSH / HANDLE 的 specs 是裸 tuple，
		// 形状 `((effect-name handler-fn-index) ...)`（对应 Python 的
		// `tuple[(Symbol, int), ...]`），而不是 `handler_specs` 操作数类型。
		result := make([]HandlerSpec, 0, len(specs))
		for _, item := range specs {
			if spec, ok := handlerSpecFromValue(item); ok {
				result = append(result, spec)
			}
		}
		return result
	}
	return nil
}

// handlerSpecFromValue 还原单个 `(effect handler-fn)` 规格。
func handlerSpecFromValue(value Value) (HandlerSpec, bool) {
	switch item := value.(type) {
	case []Value:
		if len(item) >= 2 {
			if symbol, ok := item[0].(*Symbol); ok {
				return HandlerSpec{Effect: symbol.Name, HandlerFn: intOf(item[1])}, true
			}
		}
	case *TupleValue:
		if len(item.Items) >= 2 {
			if symbol, ok := item.Items[0].(*Symbol); ok {
				return HandlerSpec{Effect: symbol.Name, HandlerFn: intOf(item.Items[1])}, true
			}
		}
	}
	return HandlerSpec{}, false
}

func importSpecsOf(value Value) []ImportSpec {
	specs, ok := value.([]ImportSpec)
	if !ok {
		return nil
	}
	return specs
}

// regTupleOf 还原寄存器下标元组（对应 TS `asNumberArray`）。
func regTupleOf(value Value) []int {
	switch tuple := value.(type) {
	case []int:
		return tuple
	case []Value:
		result := make([]int, 0, len(tuple))
		for _, item := range tuple {
			result = append(result, intOf(item))
		}
		return result
	}
	return nil
}

// sequenceToArgs 归一 APPLY 的实参序列（`_sequence_to_args`）。
//
// 注意字面量拼写（Symbol "1"）会被还原为字面量值 —— 语料 01 依赖它。
func sequenceToArgs(value Value) []Value {
	switch sequence := value.(type) {
	case []Value:
		result := make([]Value, 0, len(sequence))
		for _, item := range sequence {
			result = append(result, normalizeArgument(item))
		}
		return result
	case *TupleValue:
		result := make([]Value, 0, len(sequence.Items))
		for _, item := range sequence.Items {
			result = append(result, normalizeArgument(item))
		}
		return result
	case *ListValue:
		result := make([]Value, 0, len(sequence.Items))
		for _, item := range sequence.Items {
			result = append(result, normalizeArgument(item))
		}
		return result
	case *Chain:
		items, err := ChainToSlice(sequence)
		if err != nil {
			return nil
		}
		result := make([]Value, 0, len(items))
		for _, item := range items {
			result = append(result, normalizeArgument(item))
		}
		return result
	case *StringValue:
		return []Value{normalizeArgument(sequence)}
	case NilValue:
		return nil
	}
	return []Value{normalizeArgument(value)}
}

// normalizeArgument 把字面量拼写的 Symbol 还原成字面量值。
func normalizeArgument(value Value) Value {
	symbol, ok := value.(*Symbol)
	if !ok {
		return value
	}
	if DefaultLiteralType(symbol.Name) == "" {
		return value
	}
	if literal, ok := tryDefaultLiteral(symbol.Name); ok {
		return literal
	}
	return value
}

// CoreTruthy 是语言核的 nil-only 真值（`machine.py::_truthy`），JUMP_IF_FALSE 使用。
func CoreTruthy(value Value) bool { return !IsNil(value) }
