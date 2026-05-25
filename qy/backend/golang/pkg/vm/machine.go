package vm

import (
	"fmt"
	"os"
	"strconv"
	"sync"

	"github.com/aspect-build/qy-vm/pkg/bytecode"
)

type VM struct {
	Program *bytecode.Program
	Modules map[string]*Module
	Debug   bool
	mu      sync.Mutex
}

type Module struct {
	Name     string
	Bindings map[string]Value
	Exports  []string
}

type ExecuteResult struct {
	Value  Value
	Effect *EffectSignal
}

type tailCallRequest struct {
	funcVal *FunctionValue
	args    []Value
}

func NewVM(program *bytecode.Program) *VM {
	return &VM{
		Program: program,
		Modules: make(map[string]*Module),
	}
}

func (vm *VM) Execute(env *SymbolSpace) (Value, error) {
	mainFn := &vm.Program.Functions[vm.Program.Main]
	fv := &FunctionValue{FuncIndex: vm.Program.Main, Closure: env}
	result, err := vm.runFunction(fv, mainFn, nil, env)
	if err != nil {
		return nil, err
	}
	if result.Effect != nil {
		return nil, fmt.Errorf("unhandled effect: %s (arg: %v)", result.Effect.Effect, result.Effect.Arg)
	}
	return result.Value, nil
}

func (vm *VM) runFunction(fv *FunctionValue, fn *bytecode.Function, args []Value, callerEnv *SymbolSpace) (*ExecuteResult, error) {
	frame := vm.makeFrame(fv, fn, args)
	for {
		result, err := vm.executeFrame(frame)
		if err != nil {
			return nil, err
		}
		if result != nil {
			return result, nil
		}
	}
}

func (vm *VM) makeFrame(fv *FunctionValue, fn *bytecode.Function, args []Value) *Frame {
	env := fv.Closure.Child()
	for i, param := range fn.Params {
		if i < len(args) {
			env.Define(param, args[i])
		}
	}
	return &Frame{
		FunctionValue: fv,
		Function:      fn,
		PC:            0,
		Registers:     make([]Value, fn.RegisterCount),
		Env:           env,
		Parents:       nil,
		Results:       nil,
	}
}

func (vm *VM) executeFrame(frame *Frame) (*ExecuteResult, error) {
	for frame.PC < len(frame.Function.Instructions) {
		instr := &frame.Function.Instructions[frame.PC]
		frame.PC++

		if vm.Debug {
			fmt.Fprintf(os.Stderr, "  [%s] pc=%d op=%s\n", frame.Function.Name, frame.PC-1, instr.Opcode)
		}

		result, err := vm.executeInstruction(frame, instr)
		if err != nil {
			if effect, ok := err.(*EffectSignal); ok {
				return &ExecuteResult{Effect: effect}, nil
			}
			return nil, err
		}
		if result != nil {
			switch r := result.(type) {
			case *ExecuteResult:
				return r, nil
			case *tailCallRequest:
				fn := &vm.Program.Functions[r.funcVal.FuncIndex]
				newFrame := vm.makeFrame(r.funcVal, fn, r.args)
				*frame = *newFrame
			}
		}
	}
	return &ExecuteResult{Value: QyNil}, nil
}

func (vm *VM) executeInstruction(frame *Frame, instr *bytecode.Instruction) (interface{}, error) {
	ops := instr.Operands
	switch instr.Opcode {
	case bytecode.OpLoadHost:
		dest := ops[0].AsReg()
		frame.Registers[dest] = vm.decodeHostValue(&ops[1])

	case bytecode.OpLoadEnv:
		dest := ops[0].AsReg()
		sym := ops[1].AsString()
		val, ok := frame.Env.Resolve(sym)
		if !ok {
			return nil, fmt.Errorf("unresolved symbol: %s", sym)
		}
		frame.Registers[dest] = val

	case bytecode.OpMove:
		dest := ops[0].AsReg()
		src := ops[1].AsReg()
		frame.Registers[dest] = frame.Registers[src]

	case bytecode.OpStoreLocal:
		sym := ops[0].AsString()
		src := ops[1].AsReg()
		val := frame.Registers[src]
		if val == CompileTimeMacro {
			return nil, nil
		}
		frame.Env.Define(sym, val)

	case bytecode.OpDefineOnce:
		sym := ops[0].AsString()
		src := ops[1].AsReg()
		val := frame.Registers[src]
		if val == CompileTimeMacro {
			return nil, nil
		}
		frame.Env.DefineOnce(sym, val)

	case bytecode.OpMakeFunction:
		dest := ops[0].AsReg()
		fnIdx := ops[1].AsInt()
		frame.Registers[dest] = &FunctionValue{FuncIndex: fnIdx, Closure: frame.Env}

	case bytecode.OpMakeMacro:
		dest := ops[0].AsReg()
		frame.Registers[dest] = CompileTimeMacro

	case bytecode.OpEnterScope:
		frame.Parents = append(frame.Parents, frame.Env)
		frame.Env = frame.Env.Child()

	case bytecode.OpExitScope:
		if len(frame.Parents) > 0 {
			frame.Env = frame.Parents[len(frame.Parents)-1]
			frame.Parents = frame.Parents[:len(frame.Parents)-1]
		}

	case bytecode.OpAppendResult:
		src := ops[0].AsReg()
		val := frame.Registers[src]
		if val == CompileTimeMacro {
			val = nil
		}
		frame.Results = append(frame.Results, val)

	case bytecode.OpBuildTuple:
		dest := ops[0].AsReg()
		values := make([]Value, len(ops)-1)
		for i := 1; i < len(ops); i++ {
			values[i-1] = frame.Registers[ops[i].AsReg()]
		}
		frame.Registers[dest] = values

	case bytecode.OpCall:
		dest := ops[0].AsReg()
		calleeReg := ops[1].AsReg()
		argRegs := ops[2].AsRegTuple()
		callee := frame.Registers[calleeReg]
		args := make([]Value, len(argRegs))
		for i, r := range argRegs {
			args[i] = frame.Registers[r]
		}
		result, err := vm.call(callee, args, frame)
		if err != nil {
			if effect, ok := err.(*EffectSignal); ok {
				if effect.Continuation == nil {
					captured := frame.Capture(dest)
					cont := &Continuation{
						Effect:    effect.Effect,
						Resumable: true,
						Frame:     captured,
						DestReg:   dest,
					}
					effect.Continuation = cont
				}
				return &ExecuteResult{Effect: effect}, nil
			}
			return nil, err
		}
		frame.Registers[dest] = result

	case bytecode.OpTailCall:
		calleeReg := ops[0].AsReg()
		argRegs := ops[1].AsRegTuple()
		callee := frame.Registers[calleeReg]
		args := make([]Value, len(argRegs))
		for i, r := range argRegs {
			args[i] = frame.Registers[r]
		}
		switch c := callee.(type) {
		case *FunctionValue:
			return &tailCallRequest{funcVal: c, args: args}, nil
		default:
			result, err := vm.call(callee, args, frame)
			if err != nil {
				return nil, err
			}
			return &ExecuteResult{Value: result}, nil
		}

	case bytecode.OpReturn:
		src := ops[0].AsReg()
		val := frame.Registers[src]
		if val == CompileTimeMacro {
			val = nil
		}
		return &ExecuteResult{Value: val}, nil

	case bytecode.OpJump:
		target := ops[0].AsInt()
		frame.PC = target

	case bytecode.OpJumpIfFalse:
		src := ops[0].AsReg()
		target := ops[1].AsInt()
		if !IsTruthy(frame.Registers[src]) {
			frame.PC = target
		}

	case bytecode.OpApply:
		dest := ops[0].AsReg()
		funcReg := ops[1].AsReg()
		argsReg := ops[2].AsReg()
		callee := frame.Registers[funcReg]
		argVal := frame.Registers[argsReg]
		args := valueToArgs(argVal)
		result, err := vm.call(callee, args, frame)
		if err != nil {
			if effect, ok := err.(*EffectSignal); ok {
				return &ExecuteResult{Effect: effect}, nil
			}
			return nil, err
		}
		frame.Registers[dest] = result

	case bytecode.OpDefeffect:
		name := ops[0].AsString()
		resumable := true
		if len(ops) > 1 {
			resumable = ops[1].AsBool()
		}
		frame.Env.Define(name, &EffectDefinition{Name: name, Resumable: resumable})

	case bytecode.OpPerform:
		dest := ops[0].AsReg()
		effectSym := ops[1].AsString()
		argReg := ops[2].AsReg()
		arg := frame.Registers[argReg]

		resumable := true
		if ed, ok := frame.Env.Resolve(effectSym); ok {
			if def, ok := ed.(*EffectDefinition); ok {
				resumable = def.Resumable
			}
		}

		if !resumable {
			return nil, &EffectSignal{
				Effect:       effectSym,
				Arg:          arg,
				Continuation: nil,
				Resumable:    false,
			}
		}

		captured := frame.Capture(dest)
		cont := &Continuation{
			Effect:    effectSym,
			Resumable: true,
			Frame:     captured,
			DestReg:   dest,
		}
		return nil, &EffectSignal{
			Effect:       effectSym,
			Arg:          arg,
			Continuation: cont,
			Resumable:    true,
		}

	case bytecode.OpHandle:
		dest := ops[0].AsReg()
		bodyFnIdx := ops[1].AsInt()
		handlerSpecs := ops[2].AsHandlerSpecs()
		result, err := vm.handleEffect(bodyFnIdx, handlerSpecs, frame.Env)
		if err != nil {
			if effect, ok := err.(*EffectSignal); ok {
				return &ExecuteResult{Effect: effect}, nil
			}
			return nil, err
		}
		frame.Registers[dest] = result

	case bytecode.OpResume:
		dest := ops[0].AsReg()
		contReg := ops[1].AsReg()
		valueReg := ops[2].AsReg()
		cont, ok := frame.Registers[contReg].(*Continuation)
		if !ok {
			return nil, fmt.Errorf("resume expects a continuation, got %T", frame.Registers[contReg])
		}
		val := frame.Registers[valueReg]
		result, err := vm.resumeContinuation(cont, val)
		if err != nil {
			if effect, ok := err.(*EffectSignal); ok {
				return &ExecuteResult{Effect: effect}, nil
			}
			return nil, err
		}
		frame.Registers[dest] = result

	case bytecode.OpRaiseEffect:
		effectSym := ops[0].AsString()
		payloadReg := ops[1].AsReg()
		resumable := false
		if len(ops) > 2 {
			resumable = ops[2].AsBool()
		}
		payload := frame.Registers[payloadReg]
		return nil, &EffectSignal{
			Effect:       effectSym,
			Arg:          payload,
			Continuation: nil,
			Resumable:    resumable,
		}

	case bytecode.OpDefineModule:
		dest := ops[0].AsReg()
		moduleName := ops[1].AsString()
		fnIdx := ops[2].AsInt()
		exportNames := ops[3].AsSymbolTuple()
		result, err := vm.defineModule(moduleName, fnIdx, exportNames, frame.Env)
		if err != nil {
			return nil, err
		}
		frame.Registers[dest] = result

	case bytecode.OpFromImport:
		moduleName := ops[0].AsString()
		specs := ops[1].AsImportSpecs()
		vm.fromImport(moduleName, specs, frame.Env)

	case bytecode.OpParallelGather:
		dest := ops[0].AsReg()
		thunkIndices := make([]int, len(ops)-1)
		for i := 1; i < len(ops); i++ {
			thunkIndices[i-1] = ops[i].AsInt()
		}
		result, err := vm.parallelGather(thunkIndices, frame.Env)
		if err != nil {
			return nil, err
		}
		frame.Registers[dest] = result

	case bytecode.OpAllGather:
		dest := ops[0].AsReg()
		thunkIndices := make([]int, len(ops)-1)
		for i := 1; i < len(ops); i++ {
			thunkIndices[i-1] = ops[i].AsInt()
		}
		result, err := vm.allGather(thunkIndices, frame.Env)
		if err != nil {
			return nil, err
		}
		frame.Registers[dest] = result

	case bytecode.OpRaceFirst:
		dest := ops[0].AsReg()
		thunkIndices := make([]int, len(ops)-1)
		for i := 1; i < len(ops); i++ {
			thunkIndices[i-1] = ops[i].AsInt()
		}
		result, err := vm.raceFirst(thunkIndices, frame.Env)
		if err != nil {
			return nil, err
		}
		frame.Registers[dest] = result

	case bytecode.OpCacheEval:
		dest := ops[0].AsReg()
		thunkReg := ops[1].AsReg()
		thunkIdx, ok := frame.Registers[thunkReg].(int)
		if !ok {
			if fv, ok := frame.Registers[thunkReg].(*FunctionValue); ok {
				thunkIdx = fv.FuncIndex
			} else {
				thunkIdx = ops[1].AsInt()
			}
		}
		fn := &vm.Program.Functions[thunkIdx]
		fv := &FunctionValue{FuncIndex: thunkIdx, Closure: frame.Env}
		r, err := vm.runFunction(fv, fn, nil, frame.Env)
		if err != nil {
			return nil, err
		}
		frame.Registers[dest] = r.Value

	case bytecode.OpRuntimeEval:
		dest := ops[0].AsReg()
		exprReg := ops[1].AsReg()
		expr := frame.Registers[exprReg]
		result := vm.runtimeEval(expr, frame.Env)
		frame.Registers[dest] = result
	}

	return nil, nil
}

func (vm *VM) call(callee Value, args []Value, frame *Frame) (Value, error) {
	switch c := callee.(type) {
	case *FunctionValue:
		fn := &vm.Program.Functions[c.FuncIndex]
		result, err := vm.runFunction(c, fn, args, frame.Env)
		if err != nil {
			return nil, err
		}
		if result.Effect != nil {
			return nil, result.Effect
		}
		return result.Value, nil
	case *HostFunction:
		return c.Fn(args)
	case *EnvHostFunction:
		env := frame.Env
		if frame == nil {
			env = nil
		}
		return c.Fn(args, env)
	default:
		return nil, fmt.Errorf("cannot call value of type %T", callee)
	}
}

func (vm *VM) handleEffect(bodyFnIdx int, specs []bytecode.HandlerSpec, env *SymbolSpace) (Value, error) {
	fn := &vm.Program.Functions[bodyFnIdx]
	fv := &FunctionValue{FuncIndex: bodyFnIdx, Closure: env}
	result, err := vm.runFunction(fv, fn, nil, env)
	if err != nil {
		if effect, ok := err.(*EffectSignal); ok {
			return vm.dispatchEffect(effect, specs, env)
		}
		return nil, err
	}
	if result.Effect != nil {
		return vm.dispatchEffect(result.Effect, specs, env)
	}
	return result.Value, nil
}

func (vm *VM) dispatchEffect(signal *EffectSignal, specs []bytecode.HandlerSpec, env *SymbolSpace) (Value, error) {
	for {
		var handlerFnIdx int = -1
		for _, spec := range specs {
			if spec.Effect == signal.Effect {
				handlerFnIdx = spec.HandlerFn
				break
			}
		}
		if handlerFnIdx < 0 {
			return nil, signal
		}

		fn := &vm.Program.Functions[handlerFnIdx]
		fv := &FunctionValue{FuncIndex: handlerFnIdx, Closure: env}
		var handlerArgs []Value
		if signal.Continuation != nil {
			handlerArgs = []Value{signal.Arg, signal.Continuation}
		} else {
			handlerArgs = []Value{signal.Arg, QyNil}
		}
		result, err := vm.runFunction(fv, fn, handlerArgs, env)
		if err != nil {
			if nested, ok := err.(*EffectSignal); ok {
				found := false
				for _, spec := range specs {
					if spec.Effect == nested.Effect {
						found = true
						break
					}
				}
				if !found {
					return nil, nested
				}
				signal = nested
				continue
			}
			return nil, err
		}
		if result.Effect != nil {
			found := false
			for _, spec := range specs {
				if spec.Effect == result.Effect.Effect {
					found = true
					break
				}
			}
			if !found {
				return nil, result.Effect
			}
			signal = result.Effect
			continue
		}
		return result.Value, nil
	}
}

func (vm *VM) resumeContinuation(cont *Continuation, value Value) (Value, error) {
	if !cont.Resumable {
		return nil, fmt.Errorf("cannot resume non-resumable continuation")
	}
	resumeFrame := cont.Frame.RestoreFrame(value, cont.DestReg)
	for {
		result, err := vm.executeFrame(resumeFrame)
		if err != nil {
			return nil, err
		}
		if result != nil {
			if result.Effect != nil {
				return nil, result.Effect
			}
			return result.Value, nil
		}
	}
}

func (vm *VM) defineModule(name string, fnIdx int, exportNames []string, env *SymbolSpace) (Value, error) {
	fn := &vm.Program.Functions[fnIdx]
	modEnv := env.Child()
	fv := &FunctionValue{FuncIndex: fnIdx, Closure: modEnv}
	frame := vm.makeFrame(fv, fn, nil)
	for {
		result, err := vm.executeFrame(frame)
		if err != nil {
			return nil, err
		}
		if result != nil {
			break
		}
	}
	mod := &Module{
		Name:     name,
		Bindings: frame.Env.Bindings(),
		Exports:  exportNames,
	}
	vm.Modules[name] = mod
	return QyT, nil
}

func (vm *VM) fromImport(moduleName string, specs []bytecode.ImportSpec, env *SymbolSpace) {
	mod, ok := vm.Modules[moduleName]
	if !ok {
		return
	}
	for _, spec := range specs {
		if val, exists := mod.Bindings[spec.Name]; exists {
			env.Define(spec.Alias, val)
		}
	}
}

func (vm *VM) parallelGather(thunkIndices []int, env *SymbolSpace) ([]Value, error) {
	results := make([]Value, len(thunkIndices))
	errors := make([]error, len(thunkIndices))
	var wg sync.WaitGroup

	for i, idx := range thunkIndices {
		wg.Add(1)
		go func(i, idx int) {
			defer wg.Done()
			fn := &vm.Program.Functions[idx]
			childEnv := env.Child()
			fv := &FunctionValue{FuncIndex: idx, Closure: childEnv}
			result, err := vm.runFunction(fv, fn, nil, childEnv)
			if err != nil {
				errors[i] = err
				return
			}
			if result.Effect != nil {
				errors[i] = result.Effect
				return
			}
			results[i] = result.Value
		}(i, idx)
	}
	wg.Wait()

	for _, err := range errors {
		if err != nil {
			return nil, err
		}
	}
	return results, nil
}

func (vm *VM) allGather(thunkIndices []int, env *SymbolSpace) ([]Value, error) {
	return vm.parallelGather(thunkIndices, env)
}

func (vm *VM) raceFirst(thunkIndices []int, env *SymbolSpace) (Value, error) {
	if len(thunkIndices) == 0 {
		return QyNil, nil
	}
	type raceResult struct {
		value Value
		err   error
	}
	ch := make(chan raceResult, len(thunkIndices))
	for _, idx := range thunkIndices {
		go func(idx int) {
			fn := &vm.Program.Functions[idx]
			childEnv := env.Child()
			fv := &FunctionValue{FuncIndex: idx, Closure: childEnv}
			result, err := vm.runFunction(fv, fn, nil, childEnv)
			if err != nil {
				ch <- raceResult{err: err}
				return
			}
			if result.Effect != nil {
				ch <- raceResult{err: result.Effect}
				return
			}
			ch <- raceResult{value: result.Value}
		}(idx)
	}
	first := <-ch
	return first.value, first.err
}

func (vm *VM) runtimeEval(expr Value, env *SymbolSpace) Value {
	switch e := expr.(type) {
	case *Symbol:
		if val, ok := env.Resolve(e.Name); ok {
			return val
		}
		if n, err := strconv.ParseFloat(e.Name, 64); err == nil {
			if n == float64(int(n)) {
				return int(n)
			}
			return n
		}
		return e
	case *Chain:
		return vm.evalChain(e, env)
	case int, float64, string:
		return e
	default:
		return expr
	}
}

func (vm *VM) evalChain(chain *Chain, env *SymbolSpace) Value {
	head := chain.Head
	var fnName string
	switch h := head.(type) {
	case *Symbol:
		fnName = h.Name
	default:
		return QyNil
	}

	callee, ok := env.Resolve(fnName)
	if !ok {
		return QyNil
	}

	var args []Value
	current := chain.Tail
	for {
		c, ok := current.(*Chain)
		if !ok {
			break
		}
		args = append(args, vm.runtimeEval(c.Head, env))
		current = c.Tail
	}

	result, err := vm.call(callee, args, nil)
	if err != nil {
		return QyNil
	}
	return result
}

func (vm *VM) decodeHostValue(op *bytecode.Operand) Value {
	switch op.Type {
	case "nil":
		return QyNil
	case "t":
		return QyT
	case "bool":
		if op.AsBool() {
			return QyT
		}
		return QyNil
	case "int":
		return op.AsInt()
	case "float":
		return op.AsFloat()
	case "string":
		return op.AsString()
	case "symbol":
		return &Symbol{Name: op.AsString()}
	case "chain":
		return vm.decodeChain(op.Value)
	case "effect_def":
		m := op.Value.(map[string]interface{})
		return &EffectDefinition{
			Name:      m["name"].(string),
			Resumable: m["resumable"].(bool),
		}
	case "tuple":
		arr := op.Value.([]interface{})
		result := make([]Value, len(arr))
		for i, item := range arr {
			m := item.(map[string]interface{})
			o := &bytecode.Operand{Type: m["type"].(string), Value: m["value"]}
			result[i] = vm.decodeHostValue(o)
		}
		return result
	case "list":
		arr := op.Value.([]interface{})
		result := make([]Value, len(arr))
		for i, item := range arr {
			m := item.(map[string]interface{})
			o := &bytecode.Operand{Type: m["type"].(string), Value: m["value"]}
			result[i] = vm.decodeHostValue(o)
		}
		return result
	default:
		return QyNil
	}
}

func (vm *VM) decodeChain(v interface{}) Value {
	if v == nil {
		return QyNil
	}
	m, ok := v.(map[string]interface{})
	if !ok {
		return QyNil
	}
	if _, hasHead := m["head"]; !hasHead {
		op := &bytecode.Operand{Type: m["type"].(string), Value: m["value"]}
		return vm.decodeHostValue(op)
	}
	headMap, ok := m["head"].(map[string]interface{})
	if !ok {
		return QyNil
	}
	headOp := &bytecode.Operand{Type: headMap["type"].(string), Value: headMap["value"]}
	head := vm.decodeHostValue(headOp)
	tail := vm.decodeChain(m["tail"])
	return &Chain{Head: head, Tail: tail}
}

func valueToArgs(v Value) []Value {
	switch val := v.(type) {
	case *Chain:
		var args []Value
		current := Value(val)
		for {
			c, ok := current.(*Chain)
			if !ok {
				break
			}
			args = append(args, c.Head)
			current = c.Tail
		}
		return args
	case []Value:
		return val
	default:
		return []Value{v}
	}
}
