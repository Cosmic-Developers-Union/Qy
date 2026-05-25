package vm

import "fmt"

type Value = interface{}

type qyNilType struct{}
type qyTType struct{}

var QyNil Value = &qyNilType{}
var QyT Value = &qyTType{}

func (n *qyNilType) String() string { return "nil" }
func (t *qyTType) String() string   { return "T" }

type Symbol struct {
	Name string
}

func (s *Symbol) String() string { return s.Name }

type Chain struct {
	Head Value
	Tail Value
}

func (c *Chain) String() string {
	return fmt.Sprintf("(%v . %v)", c.Head, c.Tail)
}

type FunctionValue struct {
	FuncIndex int
	Closure   *SymbolSpace
}

type HostFunction struct {
	Name string
	Fn   func(args []Value) (Value, error)
}

type EnvHostFunction struct {
	Name string
	Fn   func(args []Value, env *SymbolSpace) (Value, error)
}

func (h *HostFunction) String() string { return fmt.Sprintf("<host:%s>", h.Name) }

type EffectDefinition struct {
	Name      string
	Resumable bool
}

type Continuation struct {
	Effect    string
	Resumable bool
	Frame     *CapturedFrame
	DestReg   int
}

type compileMacroSentinel struct{}

var CompileTimeMacro Value = &compileMacroSentinel{}

func IsTruthy(v Value) bool {
	if v == nil || v == QyNil {
		return false
	}
	if b, ok := v.(bool); ok {
		return b
	}
	return true
}

func IsNil(v Value) bool {
	return v == nil || v == QyNil
}

func ValueToString(v Value) string {
	if v == nil || v == QyNil {
		return "nil"
	}
	if v == QyT {
		return "T"
	}
	switch val := v.(type) {
	case *qyTType:
		return "T"
	case *qyNilType:
		return "nil"
	case bool:
		if val {
			return "T"
		}
		return "nil"
	case int:
		return fmt.Sprintf("%d", val)
	case float64:
		return fmt.Sprintf("%g", val)
	case string:
		return val
	case *Symbol:
		return val.Name
	case *Chain:
		return chainToString(val)
	case *FunctionValue:
		return "<function>"
	case *HostFunction:
		return val.String()
	case *EffectDefinition:
		return fmt.Sprintf("<effect:%s>", val.Name)
	case *Continuation:
		return fmt.Sprintf("<continuation:%s>", val.Effect)
	case []Value:
		return tupleToString(val)
	default:
		return fmt.Sprintf("%v", val)
	}
}

func chainToString(c *Chain) string {
	result := "("
	current := Value(c)
	first := true
	for {
		chain, ok := current.(*Chain)
		if !ok {
			break
		}
		if !first {
			result += " "
		}
		first = false
		result += ValueToString(chain.Head)
		current = chain.Tail
	}
	if !IsNil(current) {
		result += " . " + ValueToString(current)
	}
	result += ")"
	return result
}

func tupleToString(items []Value) string {
	result := "("
	for i, item := range items {
		if i > 0 {
			result += " "
		}
		result += ValueToString(item)
	}
	result += ")"
	return result
}
