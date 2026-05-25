package stdlib

import (
	"fmt"
	"math"
	"strconv"

	"github.com/aspect-build/qy-vm/pkg/vm"
)

func Arithmetic() map[string]vm.Value {
	return map[string]vm.Value{
		"+":  &vm.HostFunction{Name: "+", Fn: add},
		"-":  &vm.HostFunction{Name: "-", Fn: sub},
		"*":  &vm.HostFunction{Name: "*", Fn: mul},
		"/":  &vm.HostFunction{Name: "/", Fn: div},
		"=":  &vm.HostFunction{Name: "=", Fn: numEq},
		"==": &vm.HostFunction{Name: "==", Fn: pyEq},
		">":  &vm.HostFunction{Name: ">", Fn: numGt},
		"<":  &vm.HostFunction{Name: "<", Fn: numLt},
		">=": &vm.HostFunction{Name: ">=", Fn: numGte},
		"<=": &vm.HostFunction{Name: "<=", Fn: numLte},
	}
}

func add(args []vm.Value) (vm.Value, error) {
	if len(args) == 0 {
		return 0, nil
	}
	result := toNumber(args[0])
	for _, arg := range args[1:] {
		result += toNumber(arg)
	}
	if result == math.Trunc(result) {
		return int(result), nil
	}
	return result, nil
}

func sub(args []vm.Value) (vm.Value, error) {
	if len(args) == 0 {
		return 0, nil
	}
	if len(args) == 1 {
		r := -toNumber(args[0])
		if r == math.Trunc(r) {
			return int(r), nil
		}
		return r, nil
	}
	result := toNumber(args[0])
	for _, arg := range args[1:] {
		result -= toNumber(arg)
	}
	if result == math.Trunc(result) {
		return int(result), nil
	}
	return result, nil
}

func mul(args []vm.Value) (vm.Value, error) {
	if len(args) == 0 {
		return 1, nil
	}
	result := toNumber(args[0])
	for _, arg := range args[1:] {
		result *= toNumber(arg)
	}
	if result == math.Trunc(result) {
		return int(result), nil
	}
	return result, nil
}

func div(args []vm.Value) (vm.Value, error) {
	if len(args) == 0 {
		return 0, nil
	}
	if len(args) == 1 {
		d := toNumber(args[0])
		if d == 0 {
			return nil, &vm.EffectSignal{
				Effect:    "divide-by-zero",
				Arg:       0,
				Resumable: true,
			}
		}
		return 1.0 / d, nil
	}
	result := toNumber(args[0])
	for _, arg := range args[1:] {
		d := toNumber(arg)
		if d == 0 {
			return nil, &vm.EffectSignal{
				Effect:    "divide-by-zero",
				Arg:       0,
				Resumable: true,
			}
		}
		result /= d
	}
	if result == math.Trunc(result) {
		return int(result), nil
	}
	return result, nil
}

func numEq(args []vm.Value) (vm.Value, error) {
	if len(args) < 2 {
		return vm.QyNil, nil
	}
	a := toNumber(args[0])
	b := toNumber(args[1])
	if a == b {
		return vm.QyT, nil
	}
	return vm.QyNil, nil
}

func pyEq(args []vm.Value) (vm.Value, error) {
	if len(args) < 2 {
		return vm.QyNil, nil
	}
	if fmt.Sprintf("%v", args[0]) == fmt.Sprintf("%v", args[1]) {
		return vm.QyT, nil
	}
	return vm.QyNil, nil
}

func numGt(args []vm.Value) (vm.Value, error) {
	if len(args) < 2 {
		return vm.QyNil, nil
	}
	if toNumber(args[0]) > toNumber(args[1]) {
		return vm.QyT, nil
	}
	return vm.QyNil, nil
}

func numLt(args []vm.Value) (vm.Value, error) {
	if len(args) < 2 {
		return vm.QyNil, nil
	}
	if toNumber(args[0]) < toNumber(args[1]) {
		return vm.QyT, nil
	}
	return vm.QyNil, nil
}

func numGte(args []vm.Value) (vm.Value, error) {
	if len(args) < 2 {
		return vm.QyNil, nil
	}
	if toNumber(args[0]) >= toNumber(args[1]) {
		return vm.QyT, nil
	}
	return vm.QyNil, nil
}

func numLte(args []vm.Value) (vm.Value, error) {
	if len(args) < 2 {
		return vm.QyNil, nil
	}
	if toNumber(args[0]) <= toNumber(args[1]) {
		return vm.QyT, nil
	}
	return vm.QyNil, nil
}

func toNumber(v vm.Value) float64 {
	switch n := v.(type) {
	case int:
		return float64(n)
	case float64:
		return n
	case bool:
		if n {
			return 1
		}
		return 0
	case *vm.Symbol:
		if f, err := strconv.ParseFloat(n.Name, 64); err == nil {
			return f
		}
		return 0
	case string:
		if f, err := strconv.ParseFloat(n, 64); err == nil {
			return f
		}
		return 0
	}
	return 0
}
