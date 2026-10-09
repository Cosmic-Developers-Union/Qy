package stdlib

import (
	"math/big"

	"github.com/Cosmic-Developers-Union/Qy/qy/backend/golang/pkg/vm"
)

// qy.int8..qy.float128 具体数值空间（对应 `qy/std/numeric_spaces.py`）。

func floorDivBig(a, b *big.Int) *big.Int {
	q := new(big.Int)
	r := new(big.Int)
	q.QuoRem(a, b, r)
	if r.Sign() != 0 && (r.Sign() < 0) != (b.Sign() < 0) {
		q.Sub(q, big.NewInt(1))
	}
	return q
}

func requireTypedInt(value vm.Value, typeName, op string) (*big.Int, error) {
	n, ok := value.(*vm.Number)
	if !ok || !n.IsInt || n.TypeName != typeName {
		return nil, vm.NewTypeError(typeName + "." + op + " expects " + typeName)
	}
	return n.BigPayload(), nil
}

func requireTypedFloat(value vm.Value, typeName, op string) (float64, error) {
	n, ok := value.(*vm.Number)
	if !ok || n.IsInt || n.TypeName != typeName {
		return 0, vm.NewTypeError(typeName + "." + op + " expects " + typeName)
	}
	return n.FloatPayload(), nil
}

func divideByZero(op string) error {
	payload := vm.NewDict([]vm.DictEntry{{Key: vm.NewSymbol("operator"), Value: vm.NewString(op)}})
	return vm.PerformEffect("divide-by-zero", payload, false)
}

func makeIntegerSpaceModule(typeName string, bits int, minValue, maxValue *big.Int) map[string]vm.Value {
	signed := minValue.Sign() < 0
	typed := func(value vm.Value, op string) (*big.Int, error) {
		return requireTypedInt(value, typeName, op)
	}
	checked := func(value *big.Int, op string) (vm.Value, error) {
		result, err := checkIntegerRange(value, typeName, op)
		if err != nil {
			return nil, err
		}
		return vm.NewIntegerOfType(typeName, result), nil
	}
	exports := map[string]vm.Value{}
	exports[typeName] = &vm.PureOperator{Name: typeName, Fn: func(args []vm.Value) (vm.Value, error) {
		n, ok := args[0].(*vm.Number)
		if !ok || !n.IsInt {
			return nil, vm.NewTypeError(typeName + " constructor expects integer")
		}
		return checked(n.BigPayload(), "constructor")
	}}
	exports[typeName+"?"] = &vm.PureOperator{Name: typeName + "?", Fn: func(args []vm.Value) (vm.Value, error) {
		n, ok := args[0].(*vm.Number)
		if ok && n.IsInt && n.TypeName == typeName {
			return vm.QyT, nil
		}
		return vm.QyNil, nil
	}}
	exports["+"] = &vm.PureOperator{Name: "+", Fn: func(args []vm.Value) (vm.Value, error) {
		total := new(big.Int)
		for _, arg := range args {
			v, err := typed(arg, "+")
			if err != nil {
				return nil, err
			}
			total.Add(total, v)
		}
		return checked(total, "+")
	}}
	exports["-"] = &vm.PureOperator{Name: "-", Fn: func(args []vm.Value) (vm.Value, error) {
		if len(args) == 1 {
			v, err := typed(args[0], "-")
			if err != nil {
				return nil, err
			}
			return checked(new(big.Int).Neg(v), "-")
		}
		result, err := typed(args[0], "-")
		if err != nil {
			return nil, err
		}
		result = new(big.Int).Set(result)
		for _, arg := range args[1:] {
			v, err := typed(arg, "-")
			if err != nil {
				return nil, err
			}
			result.Sub(result, v)
		}
		return checked(result, "-")
	}}
	exports["*"] = &vm.PureOperator{Name: "*", Fn: func(args []vm.Value) (vm.Value, error) {
		result := big.NewInt(1)
		for _, arg := range args {
			v, err := typed(arg, "*")
			if err != nil {
				return nil, err
			}
			result.Mul(result, v)
		}
		return checked(result, "*")
	}}
	exports["/"] = &vm.PureOperator{Name: "/", Fn: func(args []vm.Value) (vm.Value, error) {
		var result *big.Int
		if len(args) == 1 {
			first, err := typed(args[0], "/")
			if err != nil {
				return nil, err
			}
			if first.Sign() == 0 {
				return nil, divideByZero("/")
			}
			result = floorDivBig(big.NewInt(1), first)
		} else {
			value, err := typed(args[0], "/")
			if err != nil {
				return nil, err
			}
			result = new(big.Int).Set(value)
			for _, arg := range args[1:] {
				divisor, err := typed(arg, "/")
				if err != nil {
					return nil, err
				}
				if divisor.Sign() == 0 {
					return nil, divideByZero("/")
				}
				// big.Int.Quo 向零截断，与 qy.num 的整数 `/` 一致。
				result.Quo(result, divisor)
			}
		}
		return checked(result, "/")
	}}
	exports["mod"] = &vm.PureOperator{Name: "mod", Fn: func(args []vm.Value) (vm.Value, error) {
		left, err := typed(args[0], "mod")
		if err != nil {
			return nil, err
		}
		right, err := typed(args[1], "mod")
		if err != nil {
			return nil, err
		}
		if right.Sign() == 0 {
			return nil, divideByZero("mod")
		}
		return checked(pyMod(left, right), "mod")
	}}
	exports["rem"] = &vm.PureOperator{Name: "rem", Fn: func(args []vm.Value) (vm.Value, error) {
		left, err := typed(args[0], "rem")
		if err != nil {
			return nil, err
		}
		right, err := typed(args[1], "rem")
		if err != nil {
			return nil, err
		}
		if right.Sign() == 0 {
			return nil, divideByZero("rem")
		}
		// big.Int.Rem 向零截断（结果符号跟随被除数），与 qy.num 的 remainder 一致。
		return checked(new(big.Int).Rem(left, right), "rem")
	}}
	compare := func(op string, cmp func(c int) bool) vm.Value {
		return &vm.PureOperator{Name: op, Fn: func(args []vm.Value) (vm.Value, error) {
			left, err := typed(args[0], op)
			if err != nil {
				return nil, err
			}
			right, err := typed(args[1], op)
			if err != nil {
				return nil, err
			}
			if cmp(left.Cmp(right)) {
				return vm.QyT, nil
			}
			return vm.QyNil, nil
		}}
	}
	exports["<"] = compare("<", func(c int) bool { return c < 0 })
	exports[">"] = compare(">", func(c int) bool { return c > 0 })
	exports["<="] = compare("<=", func(c int) bool { return c <= 0 })
	exports[">="] = compare(">=", func(c int) bool { return c >= 0 })
	exports["="] = &vm.PureOperator{Name: "=", Fn: func(args []vm.Value) (vm.Value, error) {
		left, err := typed(args[0], "=")
		if err != nil {
			return vm.QyNil, nil //nolint:nilerr // 类型不符按 Python 语义返回 nil
		}
		right, err := typed(args[1], "=")
		if err != nil {
			return vm.QyNil, nil //nolint:nilerr
		}
		if left.Cmp(right) == 0 {
			return vm.QyT, nil
		}
		return vm.QyNil, nil
	}}
	bitFold := func(op string, identity int64, fold func(z, x, y *big.Int) *big.Int) vm.Value {
		return &vm.PureOperator{Name: op, Fn: func(args []vm.Value) (vm.Value, error) {
			if len(args) == 0 {
				return vm.NewIntegerOfType(typeName, big.NewInt(identity)), nil
			}
			result, err := typed(args[0], op)
			if err != nil {
				return nil, err
			}
			result = new(big.Int).Set(result)
			for _, arg := range args[1:] {
				value, err := typed(arg, op)
				if err != nil {
					return nil, err
				}
				result = fold(result, result, value)
			}
			return vm.NewIntegerOfType(typeName, result), nil
		}}
	}
	exports["bit-and"] = bitFold("bit-and", -1, func(z, x, y *big.Int) *big.Int { return z.And(x, y) })
	exports["bit-or"] = bitFold("bit-or", 0, func(z, x, y *big.Int) *big.Int { return z.Or(x, y) })
	exports["bit-xor"] = bitFold("bit-xor", 0, func(z, x, y *big.Int) *big.Int { return z.Xor(x, y) })
	exports["bit-not"] = &vm.PureOperator{Name: "bit-not", Fn: func(args []vm.Value) (vm.Value, error) {
		value, err := typed(args[0], "bit-not")
		if err != nil {
			return nil, err
		}
		mask := new(big.Int).Lsh(big.NewInt(1), uint(bits))
		mask.Sub(mask, big.NewInt(1))
		result := new(big.Int).Not(value)
		result.And(result, mask)
		if signed {
			signBit := new(big.Int).Lsh(big.NewInt(1), uint(bits-1))
			if result.Cmp(signBit) >= 0 {
				result.Sub(result, new(big.Int).Lsh(big.NewInt(1), uint(bits)))
			}
		}
		return vm.NewIntegerOfType(typeName, result), nil
	}}
	exports["shl"] = &vm.PureOperator{Name: "shl", Fn: func(args []vm.Value) (vm.Value, error) {
		value, err := typed(args[0], "shl")
		if err != nil {
			return nil, err
		}
		shift, err := typed(args[1], "shl")
		if err != nil {
			return nil, err
		}
		if !shift.IsInt64() || shift.Int64() < 0 {
			return nil, vm.NewTypeError("shl shift amount must be non-negative")
		}
		return checked(new(big.Int).Lsh(value, uint(shift.Int64())), "shl")
	}}
	exports["shr"] = &vm.PureOperator{Name: "shr", Fn: func(args []vm.Value) (vm.Value, error) {
		value, err := typed(args[0], "shr")
		if err != nil {
			return nil, err
		}
		shift, err := typed(args[1], "shr")
		if err != nil {
			return nil, err
		}
		if !shift.IsInt64() || shift.Int64() < 0 {
			return nil, vm.NewTypeError("shr shift amount must be non-negative")
		}
		return vm.NewIntegerOfType(typeName, new(big.Int).Rsh(value, uint(shift.Int64()))), nil
	}}
	exports["min-value"] = vm.NewIntegerOfType(typeName, minValue)
	exports["max-value"] = vm.NewIntegerOfType(typeName, maxValue)
	exports["bits"] = vm.NewInt(int64(bits))
	return exports
}

func makeFloatSpaceModule(typeName string, bits int) map[string]vm.Value {
	typed := func(value vm.Value, op string) (float64, error) {
		return requireTypedFloat(value, typeName, op)
	}
	finite := func(value float64, op string) (vm.Value, error) {
		checked, err := checkFloatFinite(value, typeName, op)
		if err != nil {
			return nil, err
		}
		return vm.NewFloatOfType(typeName, checked), nil
	}
	exports := map[string]vm.Value{}
	exports[typeName] = &vm.PureOperator{Name: typeName, Fn: func(args []vm.Value) (vm.Value, error) {
		n, ok := args[0].(*vm.Number)
		if !ok {
			return nil, vm.NewTypeError(typeName + " constructor expects number")
		}
		var raw float64
		if n.IsInt {
			value, _ := new(big.Float).SetInt(n.BigPayload()).Float64()
			raw = value
		} else {
			raw = n.FloatPayload()
		}
		return finite(raw, "constructor")
	}}
	exports[typeName+"?"] = &vm.PureOperator{Name: typeName + "?", Fn: func(args []vm.Value) (vm.Value, error) {
		n, ok := args[0].(*vm.Number)
		if ok && !n.IsInt && n.TypeName == typeName {
			return vm.QyT, nil
		}
		return vm.QyNil, nil
	}}
	exports["+"] = &vm.PureOperator{Name: "+", Fn: func(args []vm.Value) (vm.Value, error) {
		total := 0.0
		for _, arg := range args {
			value, err := typed(arg, "+")
			if err != nil {
				return nil, err
			}
			total += value
		}
		return finite(total, "+")
	}}
	exports["-"] = &vm.PureOperator{Name: "-", Fn: func(args []vm.Value) (vm.Value, error) {
		if len(args) == 1 {
			value, err := typed(args[0], "-")
			if err != nil {
				return nil, err
			}
			return vm.NewFloatOfType(typeName, -value), nil
		}
		result, err := typed(args[0], "-")
		if err != nil {
			return nil, err
		}
		for _, arg := range args[1:] {
			value, err := typed(arg, "-")
			if err != nil {
				return nil, err
			}
			result -= value
		}
		return finite(result, "-")
	}}
	exports["*"] = &vm.PureOperator{Name: "*", Fn: func(args []vm.Value) (vm.Value, error) {
		result := 1.0
		for _, arg := range args {
			value, err := typed(arg, "*")
			if err != nil {
				return nil, err
			}
			result *= value
		}
		return finite(result, "*")
	}}
	exports["/"] = &vm.PureOperator{Name: "/", Fn: func(args []vm.Value) (vm.Value, error) {
		var result float64
		if len(args) == 1 {
			first, err := typed(args[0], "/")
			if err != nil {
				return nil, err
			}
			if first == 0 {
				return nil, divideByZero("/")
			}
			result = 1 / first
		} else {
			value, err := typed(args[0], "/")
			if err != nil {
				return nil, err
			}
			result = value
			for _, arg := range args[1:] {
				divisor, err := typed(arg, "/")
				if err != nil {
					return nil, err
				}
				if divisor == 0 {
					return nil, divideByZero("/")
				}
				result /= divisor
			}
		}
		return finite(result, "/")
	}}
	compare := func(op string, cmp func(c int) bool) vm.Value {
		return &vm.PureOperator{Name: op, Fn: func(args []vm.Value) (vm.Value, error) {
			left, err := typed(args[0], op)
			if err != nil {
				return nil, err
			}
			right, err := typed(args[1], op)
			if err != nil {
				return nil, err
			}
			c := 0
			if left < right {
				c = -1
			} else if left > right {
				c = 1
			}
			if cmp(c) {
				return vm.QyT, nil
			}
			return vm.QyNil, nil
		}}
	}
	exports["<"] = compare("<", func(c int) bool { return c < 0 })
	exports[">"] = compare(">", func(c int) bool { return c > 0 })
	exports["<="] = compare("<=", func(c int) bool { return c <= 0 })
	exports[">="] = compare(">=", func(c int) bool { return c >= 0 })
	exports["="] = &vm.PureOperator{Name: "=", Fn: func(args []vm.Value) (vm.Value, error) {
		left, err := typed(args[0], "=")
		if err != nil {
			return vm.QyNil, nil //nolint:nilerr
		}
		right, err := typed(args[1], "=")
		if err != nil {
			return vm.QyNil, nil //nolint:nilerr
		}
		if left == right {
			return vm.QyT, nil
		}
		return vm.QyNil, nil
	}}
	exports["bits"] = vm.NewInt(int64(bits))
	return exports
}

// NumberSpaceModules 构造 qy.int8..qy.float128 全部模块。
func NumberSpaceModules() map[string]*vm.ModuleValue {
	modules := map[string]*vm.ModuleValue{}
	modules["qy.int8"] = vm.NewModuleValue("qy.int8", makeIntegerSpaceModule("int8", 8, big.NewInt(-128), big.NewInt(127)))
	modules["qy.int16"] = vm.NewModuleValue("qy.int16", makeIntegerSpaceModule("int16", 16, big.NewInt(-32768), big.NewInt(32767)))
	modules["qy.int32"] = vm.NewModuleValue("qy.int32", makeIntegerSpaceModule("int32", 32, mustBigInt("-2147483648"), mustBigInt("2147483647")))
	modules["qy.int64"] = vm.NewModuleValue("qy.int64", makeIntegerSpaceModule("int64", 64, mustBigInt("-9223372036854775808"), mustBigInt("9223372036854775807")))
	modules["qy.uint8"] = vm.NewModuleValue("qy.uint8", makeIntegerSpaceModule("uint8", 8, big.NewInt(0), big.NewInt(255)))
	modules["qy.uint16"] = vm.NewModuleValue("qy.uint16", makeIntegerSpaceModule("uint16", 16, big.NewInt(0), big.NewInt(65535)))
	modules["qy.uint32"] = vm.NewModuleValue("qy.uint32", makeIntegerSpaceModule("uint32", 32, big.NewInt(0), mustBigInt("4294967295")))
	modules["qy.uint64"] = vm.NewModuleValue("qy.uint64", makeIntegerSpaceModule("uint64", 64, big.NewInt(0), mustBigInt("18446744073709551615")))
	modules["qy.float16"] = vm.NewModuleValue("qy.float16", makeFloatSpaceModule("float16", 16))
	modules["qy.float32"] = vm.NewModuleValue("qy.float32", makeFloatSpaceModule("float32", 32))
	modules["qy.float64"] = vm.NewModuleValue("qy.float64", makeFloatSpaceModule("float64", 64))
	modules["qy.float128"] = vm.NewModuleValue("qy.float128", makeFloatSpaceModule("float128", 128))
	return modules
}
