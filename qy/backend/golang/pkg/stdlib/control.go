package stdlib

import (
	"strings"

	"github.com/Cosmic-Developers-Union/Qy/qy/backend/golang/pkg/vm"
)

// `qy.core` 的控制算子中属于运行期的部分。
//
// 真源：`qy/std/control.py`。`cond` / `let` / `define` / `defun` / `lambda` /
// `quote` / `macro` 都是编译期形式，不会出现在字节码运行期；
// 运行期真正被 LOAD_ENV 调用的是 `truthy`。

// Truthy 是标准 profile 的复合真值判断（`control.py::_complex_truthy`）。
//
// nil / none / false / () / 0 / "" / 空容器都是假。
func Truthy(value vm.Value) vm.Value {
	if vm.IsNil(value) || value == nil || vm.IsNone(value) {
		return vm.QyNil
	}
	if b, ok := value.(bool); ok {
		if !b {
			return vm.QyNil
		}
		return vm.QyT
	}
	switch v := value.(type) {
	case []vm.Value:
		if len(v) == 0 {
			return vm.QyNil
		}
	case int:
		if v == 0 {
			return vm.QyNil
		}
	case float64:
		if v == 0 {
			return vm.QyNil
		}
	case *vm.Number:
		if v.IsInt {
			if v.BigPayload().Sign() == 0 {
				return vm.QyNil
			}
		} else if v.FloatPayload() == 0 {
			return vm.QyNil
		}
	case string:
		// 注意：Python 只对宿主 str 判空（StringValue 不是 str 子类），
		// 因此 `(truthy "")` 在 Qy 语义下是 **真**（语料 39 依赖这一点）。
		if v == "" {
			return vm.QyNil
		}
	case *vm.TupleValue:
		if len(v.Items) == 0 {
			return vm.QyNil
		}
	case *vm.ListValue:
		if len(v.Items) == 0 {
			return vm.QyNil
		}
	case *vm.DictValue:
		if len(v.Entries) == 0 {
			return vm.QyNil
		}
	case *vm.SetValue:
		if len(v.Items) == 0 {
			return vm.QyNil
		}
	}
	return vm.QyT
}

// CoreTruthy 是语言核的 nil-only 真值（`machine.py::_truthy`）。
func CoreTruthy(value vm.Value) bool { return vm.CoreTruthy(value) }

// NotOp 是 `not`。
func NotOp(value vm.Value) (vm.Value, error) {
	if CoreTruthy(value) {
		return vm.QyNil, nil
	}
	return vm.QyT, nil
}

// NilPredicate 是 `nil?`。
func NilPredicate(value vm.Value) (vm.Value, error) {
	if vm.IsNil(value) {
		return vm.QyT, nil
	}
	return vm.QyNil, nil
}

// ControlBindings 返回 `qy.core` 的运行期控制算子绑定。
func ControlBindings() map[string]func(args []vm.Value) (vm.Value, error) {
	return map[string]func(args []vm.Value) (vm.Value, error){
		"truthy": func(args []vm.Value) (vm.Value, error) { return Truthy(argAt(args, 0)), nil },
		"nil?":   func(args []vm.Value) (vm.Value, error) { return NilPredicate(argAt(args, 0)) },
		"not":    func(args []vm.Value) (vm.Value, error) { return NotOp(argAt(args, 0)) },
	}
}

// -- symbol-space 显式建模算子（raw：需要当前 env） -------------------------

// ThisOp 是 `this`：返回当前 symbol-space。
func ThisOp(_ []vm.Value, env vm.Value) (vm.Value, error) {
	return env, nil
}

// SlotOp 是 `slot`：创建绑定槽位占位符。
func SlotOp(_ []vm.Value, _ vm.Value) (vm.Value, error) {
	return vm.SlotToken, nil
}

// BindOp 是 `bind`：把 symbol 与 value 绑定到指定 slot（slot 仅占位，绑定写入当前空间）。
func BindOp(args []vm.Value, env vm.Value) (vm.Value, error) {
	if len(args) != 3 {
		return nil, vm.NewArityError("bind expects a symbol, value, and slot")
	}
	name, ok := args[0].(*vm.Symbol)
	if !ok {
		return nil, vm.NewTypeError("bind expects a symbol")
	}
	symbolName := name.Name
	if strings.HasPrefix(symbolName, "'") && len(symbolName) > 1 {
		symbolName = symbolName[1:]
	}
	environment, ok := env.(*vm.Env)
	if !ok {
		return nil, vm.NewTypeError("bind expects a symbol-space")
	}
	environment.Define(symbolName, args[1])
	return args[1], nil
}

// argAt 安全取参（缺参返回 nil，与 TS 的 `args[0]` 为 undefined 对应）。
func argAt(args []vm.Value, index int) vm.Value {
	if index < 0 || index >= len(args) {
		return nil
	}
	return args[index]
}
