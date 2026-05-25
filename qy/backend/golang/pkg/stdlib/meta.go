package stdlib

import (
	"fmt"
	"sync/atomic"

	"github.com/aspect-build/qy-vm/pkg/vm"
)

var gensymCounter uint64

func Meta() map[string]vm.Value {
	return map[string]vm.Value{
		"gensym":    &vm.HostFunction{Name: "gensym", Fn: gensym},
		"slot":      &vm.HostFunction{Name: "slot", Fn: slot},
		"this":      &vm.HostFunction{Name: "this", Fn: thisOp},
		"component": &vm.HostFunction{Name: "component", Fn: component},
		"define":    &vm.HostFunction{Name: "define", Fn: identityOp},
		"lambda":    &vm.HostFunction{Name: "lambda", Fn: identityOp},
		"cond":      &vm.HostFunction{Name: "cond", Fn: identityOp},
		"let":       &vm.HostFunction{Name: "let", Fn: identityOp},
		"quote":     &vm.HostFunction{Name: "quote", Fn: identityOp},
		"eval":      &vm.HostFunction{Name: "eval", Fn: identityOp},
		"module":    &vm.HostFunction{Name: "module", Fn: identityOp},
		"from":      &vm.HostFunction{Name: "from", Fn: identityOp},
		"macro":     &vm.HostFunction{Name: "macro", Fn: identityOp},
		"defun":     &vm.HostFunction{Name: "defun", Fn: identityOp},
		"defeffect": &vm.HostFunction{Name: "defeffect", Fn: identityOp},
		"perform":   &vm.HostFunction{Name: "perform", Fn: identityOp},
		"handle":    &vm.HostFunction{Name: "handle", Fn: identityOp},
		"resume":    &vm.HostFunction{Name: "resume", Fn: identityOp},
		"apply":     &vm.HostFunction{Name: "apply", Fn: applyOp},
		"pipeline":  &vm.HostFunction{Name: "pipeline", Fn: pipeline},
		"parallel":  &vm.HostFunction{Name: "parallel", Fn: identityOp},
		"all":       &vm.HostFunction{Name: "all", Fn: identityOp},
		"race":      &vm.HostFunction{Name: "race", Fn: identityOp},
		"exports":   &vm.HostFunction{Name: "exports", Fn: identityOp},
		"on":        &vm.HostFunction{Name: "on", Fn: identityOp},
		"capture":   &vm.HostFunction{Name: "capture", Fn: identityOp},
		"bind":      &vm.EnvHostFunction{Name: "bind", Fn: bindOp},
	}
}

func gensym(args []vm.Value) (vm.Value, error) {
	n := atomic.AddUint64(&gensymCounter, 1)
	name := fmt.Sprintf("__gsym_%d", n)
	return &vm.Symbol{Name: name}, nil
}

func slot(args []vm.Value) (vm.Value, error) {
	n := atomic.AddUint64(&gensymCounter, 1)
	return &vm.Symbol{Name: fmt.Sprintf("__slot_%d", n)}, nil
}

func thisOp(args []vm.Value) (vm.Value, error) {
	return vm.QyT, nil
}

func identityOp(args []vm.Value) (vm.Value, error) {
	if len(args) > 0 {
		return args[len(args)-1], nil
	}
	return vm.QyNil, nil
}

func applyOp(args []vm.Value) (vm.Value, error) {
	if len(args) < 2 {
		return vm.QyNil, nil
	}
	return vm.QyNil, fmt.Errorf("apply should be handled by APPLY opcode")
}

func pipeline(args []vm.Value) (vm.Value, error) {
	if len(args) > 0 {
		return args[len(args)-1], nil
	}
	return vm.QyNil, nil
}

func bindOp(args []vm.Value, env *vm.SymbolSpace) (vm.Value, error) {
	if len(args) < 2 {
		return vm.QyNil, nil
	}
	var name string
	switch s := args[0].(type) {
	case *vm.Symbol:
		name = s.Name
	case string:
		name = s
	default:
		return vm.QyNil, fmt.Errorf("bind: first arg must be symbol, got %T", args[0])
	}
	value := args[1]
	if env != nil {
		env.Define(name, value)
	}
	return value, nil
}

func component(args []vm.Value) (vm.Value, error) {
	if len(args) < 2 {
		return vm.QyNil, nil
	}
	return &vm.HostFunction{
		Name: "component-result",
		Fn: func(innerArgs []vm.Value) (vm.Value, error) {
			result := vm.Value(nil)
			for i := len(args) - 1; i >= 0; i-- {
				fn := args[i]
				var callArgs []vm.Value
				if result == nil {
					callArgs = innerArgs
				} else {
					callArgs = []vm.Value{result}
				}
				switch f := fn.(type) {
				case *vm.HostFunction:
					var err error
					result, err = f.Fn(callArgs)
					if err != nil {
						return nil, err
					}
				default:
					return nil, fmt.Errorf("component: cannot call %T", fn)
				}
			}
			return result, nil
		},
	}, nil
}
