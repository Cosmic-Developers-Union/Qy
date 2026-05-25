package stdlib

import (
	"fmt"

	"github.com/aspect-build/qy-vm/pkg/vm"
)

func Data() map[string]vm.Value {
	return map[string]vm.Value{
		"car":    &vm.HostFunction{Name: "car", Fn: car},
		"cdr":    &vm.HostFunction{Name: "cdr", Fn: cdr},
		"cons":   &vm.HostFunction{Name: "cons", Fn: cons},
		"atom":   &vm.HostFunction{Name: "atom", Fn: atom},
		"eq":     &vm.HostFunction{Name: "eq", Fn: eq},
		"is":     &vm.HostFunction{Name: "is", Fn: isOp},
		"get":    &vm.HostFunction{Name: "get", Fn: get},
		"has?":   &vm.HostFunction{Name: "has?", Fn: has},
		"len":    &vm.HostFunction{Name: "len", Fn: length},
		"list":   &vm.HostFunction{Name: "list", Fn: list},
		"dict":   &vm.HostFunction{Name: "dict", Fn: dict},
		"tuple":  &vm.HostFunction{Name: "tuple", Fn: tuple},
		"set":    &vm.HostFunction{Name: "set", Fn: setOp},
		"type":   &vm.HostFunction{Name: "type", Fn: typeOf},
		"reify":  &vm.HostFunction{Name: "reify", Fn: reify},
		"chain":  &vm.HostFunction{Name: "chain", Fn: chainOp},
		"append": &vm.HostFunction{Name: "append", Fn: appendOp},
	}
}

func car(args []vm.Value) (vm.Value, error) {
	if len(args) < 1 {
		return vm.QyNil, nil
	}
	c, ok := args[0].(*vm.Chain)
	if !ok {
		return vm.QyNil, fmt.Errorf("car expects a chain, got %T", args[0])
	}
	return c.Head, nil
}

func cdr(args []vm.Value) (vm.Value, error) {
	if len(args) < 1 {
		return vm.QyNil, nil
	}
	c, ok := args[0].(*vm.Chain)
	if !ok {
		return vm.QyNil, fmt.Errorf("cdr expects a chain, got %T", args[0])
	}
	return c.Tail, nil
}

func cons(args []vm.Value) (vm.Value, error) {
	if len(args) < 2 {
		return vm.QyNil, nil
	}
	return &vm.Chain{Head: args[0], Tail: args[1]}, nil
}

func atom(args []vm.Value) (vm.Value, error) {
	if len(args) < 1 {
		return vm.QyT, nil
	}
	v := args[0]
	if _, ok := v.(*vm.Chain); ok {
		return vm.QyNil, nil
	}
	return vm.QyT, nil
}

func eq(args []vm.Value) (vm.Value, error) {
	if len(args) < 2 {
		return vm.QyNil, nil
	}
	a, b := args[0], args[1]
	if symbolEq(a, b) {
		return vm.QyT, nil
	}
	return vm.QyNil, nil
}

func symbolEq(a, b vm.Value) bool {
	if a == b {
		return true
	}
	if vm.IsNil(a) && vm.IsNil(b) {
		return true
	}
	sa, aIsSym := a.(*vm.Symbol)
	sb, bIsSym := b.(*vm.Symbol)
	if aIsSym && bIsSym {
		return sa.Name == sb.Name
	}
	ai, aIsInt := a.(int)
	bi, bIsInt := b.(int)
	if aIsInt && bIsInt {
		return ai == bi
	}
	af, aIsFloat := a.(float64)
	bf, bIsFloat := b.(float64)
	if aIsFloat && bIsFloat {
		return af == bf
	}
	as, aIsStr := a.(string)
	bs, bIsStr := b.(string)
	if aIsStr && bIsStr {
		return as == bs
	}
	return false
}

func isOp(args []vm.Value) (vm.Value, error) {
	if len(args) < 2 {
		return vm.QyNil, nil
	}
	if args[0] == args[1] {
		return vm.QyT, nil
	}
	return vm.QyNil, nil
}

func get(args []vm.Value) (vm.Value, error) {
	if len(args) < 2 {
		return vm.QyNil, nil
	}
	collection := args[0]
	key := args[1]

	switch c := collection.(type) {
	case []vm.Value:
		idx := toIntKey(key)
		if idx >= 0 && idx < len(c) {
			return c[idx], nil
		}
		if len(args) > 2 {
			return args[2], nil
		}
		return vm.QyNil, nil
	case *vm.Chain:
		idx := toIntKey(key)
		current := vm.Value(c)
		for i := 0; i < idx; i++ {
			chain, ok := current.(*vm.Chain)
			if !ok {
				if len(args) > 2 {
					return args[2], nil
				}
				return vm.QyNil, nil
			}
			current = chain.Tail
		}
		if chain, ok := current.(*vm.Chain); ok {
			return chain.Head, nil
		}
		if len(args) > 2 {
			return args[2], nil
		}
		return vm.QyNil, nil
	case map[string]vm.Value:
		k := valueToKey(key)
		if v, ok := c[k]; ok {
			return v, nil
		}
		if len(args) > 2 {
			return args[2], nil
		}
		return vm.QyNil, nil
	}
	if len(args) > 2 {
		return args[2], nil
	}
	return vm.QyNil, nil
}

func has(args []vm.Value) (vm.Value, error) {
	if len(args) < 2 {
		return vm.QyNil, nil
	}
	collection := args[0]
	key := args[1]

	switch c := collection.(type) {
	case []vm.Value:
		idx := toIntKey(key)
		if idx >= 0 && idx < len(c) {
			return vm.QyT, nil
		}
	case map[string]vm.Value:
		k := valueToKey(key)
		if _, ok := c[k]; ok {
			return vm.QyT, nil
		}
	}
	return vm.QyNil, nil
}

func length(args []vm.Value) (vm.Value, error) {
	if len(args) < 1 {
		return 0, nil
	}
	v := args[0]
	switch c := v.(type) {
	case []vm.Value:
		return len(c), nil
	case *vm.Chain:
		count := 0
		current := vm.Value(c)
		for {
			chain, ok := current.(*vm.Chain)
			if !ok {
				break
			}
			count++
			current = chain.Tail
		}
		return count, nil
	case map[string]vm.Value:
		return len(c), nil
	case string:
		return len(c), nil
	}
	if vm.IsNil(v) {
		return 0, nil
	}
	return 0, nil
}

func list(args []vm.Value) (vm.Value, error) {
	if len(args) == 1 {
		if c, ok := args[0].(*vm.Chain); ok {
			var result []vm.Value
			current := vm.Value(c)
			for {
				chain, ok := current.(*vm.Chain)
				if !ok {
					break
				}
				result = append(result, chain.Head)
				current = chain.Tail
			}
			return result, nil
		}
	}
	result := make([]vm.Value, len(args))
	copy(result, args)
	return result, nil
}

func dict(args []vm.Value) (vm.Value, error) {
	result := make(map[string]vm.Value)
	for i := 0; i+1 < len(args); i += 2 {
		key := valueToKey(args[i])
		result[key] = args[i+1]
	}
	return result, nil
}

func tuple(args []vm.Value) (vm.Value, error) {
	result := make([]vm.Value, len(args))
	copy(result, args)
	return result, nil
}

func setOp(args []vm.Value) (vm.Value, error) {
	result := make(map[string]vm.Value)
	for _, arg := range args {
		key := valueToKey(arg)
		result[key] = vm.QyT
	}
	return result, nil
}

func typeOf(args []vm.Value) (vm.Value, error) {
	if len(args) < 1 {
		return &vm.Symbol{Name: "nil"}, nil
	}
	v := args[0]
	switch v.(type) {
	case int:
		return &vm.Symbol{Name: "int"}, nil
	case float64:
		return &vm.Symbol{Name: "float"}, nil
	case string:
		return &vm.Symbol{Name: "string"}, nil
	case *vm.Symbol:
		return &vm.Symbol{Name: "symbol"}, nil
	case *vm.Chain:
		return &vm.Symbol{Name: "chain"}, nil
	case *vm.FunctionValue:
		return &vm.Symbol{Name: "function"}, nil
	case *vm.HostFunction:
		return &vm.Symbol{Name: "function"}, nil
	case []vm.Value:
		return &vm.Symbol{Name: "list"}, nil
	case map[string]vm.Value:
		return &vm.Symbol{Name: "dict"}, nil
	case *vm.EffectDefinition:
		return &vm.Symbol{Name: "effect"}, nil
	}
	if vm.IsNil(v) {
		return &vm.Symbol{Name: "nil"}, nil
	}
	return &vm.Symbol{Name: "unknown"}, nil
}

func reify(args []vm.Value) (vm.Value, error) {
	if len(args) < 1 {
		return vm.QyNil, nil
	}
	return reifyValue(args[0]), nil
}

func reifyValue(v vm.Value) vm.Value {
	switch val := v.(type) {
	case int:
		return &vm.Symbol{Name: fmt.Sprintf("%d", val)}
	case float64:
		return &vm.Symbol{Name: fmt.Sprintf("%g", val)}
	case string:
		return &vm.Symbol{Name: val}
	case *vm.Symbol:
		return val
	case *vm.Chain:
		return &vm.Chain{
			Head: reifyValue(val.Head),
			Tail: reifyTail(val.Tail),
		}
	case []vm.Value:
		if len(val) == 0 {
			return vm.QyNil
		}
		result := vm.Value(vm.QyNil)
		for i := len(val) - 1; i >= 0; i-- {
			result = &vm.Chain{Head: reifyValue(val[i]), Tail: result}
		}
		return result
	}
	if vm.IsNil(v) {
		return vm.QyNil
	}
	return v
}

func reifyTail(v vm.Value) vm.Value {
	if vm.IsNil(v) {
		return vm.QyNil
	}
	if c, ok := v.(*vm.Chain); ok {
		return &vm.Chain{
			Head: reifyValue(c.Head),
			Tail: reifyTail(c.Tail),
		}
	}
	return reifyValue(v)
}

func chainOp(args []vm.Value) (vm.Value, error) {
	if len(args) == 1 {
		switch v := args[0].(type) {
		case []vm.Value:
			result := vm.Value(vm.QyNil)
			for i := len(v) - 1; i >= 0; i-- {
				result = &vm.Chain{Head: v[i], Tail: result}
			}
			return result, nil
		case *vm.Chain:
			return v, nil
		}
	}
	result := vm.Value(vm.QyNil)
	for i := len(args) - 1; i >= 0; i-- {
		result = &vm.Chain{Head: args[i], Tail: result}
	}
	return result, nil
}

func appendOp(args []vm.Value) (vm.Value, error) {
	if len(args) < 2 {
		if len(args) == 1 {
			return args[0], nil
		}
		return vm.QyNil, nil
	}
	left := args[0]
	right := args[1]

	switch l := left.(type) {
	case []vm.Value:
		switch r := right.(type) {
		case []vm.Value:
			result := make([]vm.Value, 0, len(l)+len(r))
			result = append(result, l...)
			result = append(result, r...)
			return result, nil
		default:
			result := make([]vm.Value, 0, len(l)+1)
			result = append(result, l...)
			result = append(result, r)
			return result, nil
		}
	case *vm.Chain:
		var items []vm.Value
		current := vm.Value(l)
		for {
			c, ok := current.(*vm.Chain)
			if !ok {
				break
			}
			items = append(items, c.Head)
			current = c.Tail
		}
		result := right
		for i := len(items) - 1; i >= 0; i-- {
			result = &vm.Chain{Head: items[i], Tail: result}
		}
		return result, nil
	}
	return right, nil
}

func toIntKey(v vm.Value) int {
	switch n := v.(type) {
	case int:
		return n
	case float64:
		return int(n)
	}
	return 0
}

func valueToKey(v vm.Value) string {
	switch val := v.(type) {
	case string:
		return val
	case *vm.Symbol:
		return val.Name
	default:
		return fmt.Sprintf("%v", v)
	}
}
