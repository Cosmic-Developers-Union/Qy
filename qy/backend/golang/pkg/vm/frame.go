package vm

import "github.com/aspect-build/qy-vm/pkg/bytecode"

type Frame struct {
	FunctionValue *FunctionValue
	Function      *bytecode.Function
	PC            int
	Registers     []Value
	Env           *SymbolSpace
	Parents       []*SymbolSpace
	Results       []Value
}

type CapturedFrame struct {
	Registers     []Value
	Env           *SymbolSpace
	PC            int
	Parents       []*SymbolSpace
	Results       []Value
	FunctionValue *FunctionValue
	Function      *bytecode.Function
}

func (f *Frame) Capture(destReg int) *CapturedFrame {
	regsCopy := make([]Value, len(f.Registers))
	copy(regsCopy, f.Registers)

	parentsCopy := make([]*SymbolSpace, len(f.Parents))
	copy(parentsCopy, f.Parents)

	resultsCopy := make([]Value, len(f.Results))
	copy(resultsCopy, f.Results)

	return &CapturedFrame{
		Registers:     regsCopy,
		Env:           f.Env,
		PC:            f.PC,
		Parents:       parentsCopy,
		Results:       resultsCopy,
		FunctionValue: f.FunctionValue,
		Function:      f.Function,
	}
}

func (cf *CapturedFrame) RestoreFrame(resumeValue Value, destReg int) *Frame {
	regsCopy := make([]Value, len(cf.Registers))
	copy(regsCopy, cf.Registers)
	regsCopy[destReg] = resumeValue

	parentsCopy := make([]*SymbolSpace, len(cf.Parents))
	copy(parentsCopy, cf.Parents)

	resultsCopy := make([]Value, len(cf.Results))
	copy(resultsCopy, cf.Results)

	return &Frame{
		FunctionValue: cf.FunctionValue,
		Function:      cf.Function,
		PC:            cf.PC,
		Registers:     regsCopy,
		Env:           cf.Env,
		Parents:       parentsCopy,
		Results:       resultsCopy,
	}
}
