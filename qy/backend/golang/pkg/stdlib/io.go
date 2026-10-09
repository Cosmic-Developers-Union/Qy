package stdlib

import (
	"os"
	"strings"

	"github.com/Cosmic-Developers-Union/Qy/qy/backend/golang/pkg/vm"
)

// `qy.io` 模块与输出原语。
//
// 真源：`qy/std/io.py`（`print` / `echo` 是 EffectOperator，参数为 raw）。
//
// `_print` 的关键行为：**只**把仍是 Symbol 的字面量拼写解析为值，绝不重新求值
// 已求好的 runtime value（否则 cons 结果会被当作调用执行）。

// OutputWriter 是输出回调。
type OutputWriter func(text string)

var currentWriter OutputWriter = func(text string) {
	_, _ = os.Stdout.WriteString(text)
}

// SetOutputWriter 替换输出回调（用于宿主嵌入与测试）。
func SetOutputWriter(writer OutputWriter) {
	if writer == nil {
		currentWriter = func(string) {}
		return
	}
	currentWriter = writer
}

// GetOutputWriter 返回当前输出回调。
func GetOutputWriter() OutputWriter { return currentWriter }

func resolveLiteral(value vm.Value, _ vm.Value) vm.Value {
	symbol, ok := value.(*vm.Symbol)
	if !ok {
		return value
	}
	if vm.DefaultLiteralType(symbol.Name) == "" {
		return value
	}
	if literal, ok := vm.TryDefaultLiteral(symbol.Name); ok {
		return literal
	}
	return value
}

// PrintOp 是 `print` / `echo` / `display` 的实现体（`io.py::_print`）。
func PrintOp(args []vm.Value, env vm.Value) (vm.Value, error) {
	values := make([]vm.Value, 0, len(args))
	for _, arg := range args {
		values = append(values, resolveLiteral(arg, env))
	}
	parts := make([]string, 0, len(values))
	for _, value := range values {
		parts = append(parts, vm.FormatValue(value))
	}
	currentWriter(strings.Join(parts, " ") + "\n")
	if len(values) == 0 {
		return nil, nil
	}
	return values[len(values)-1], nil
}

// DisplayOp 是 `display`：输出但不追加换行（与后端 `display` 内建一致）。
func DisplayOp(args []vm.Value, env vm.Value) (vm.Value, error) {
	values := make([]vm.Value, 0, len(args))
	for _, arg := range args {
		values = append(values, resolveLiteral(arg, env))
	}
	parts := make([]string, 0, len(values))
	for _, value := range values {
		parts = append(parts, vm.FormatValue(value))
	}
	currentWriter(strings.Join(parts, " "))
	if len(values) == 0 {
		return nil, nil
	}
	return values[len(values)-1], nil
}

// NewlineOp 是 `newline`：只输出换行。
func NewlineOp() (vm.Value, error) {
	currentWriter("\n")
	return vm.QyNil, nil
}

// IOBindings 返回 `qy.io` 的 raw 算子绑定。
func IOBindings() map[string]func(args []vm.Value, env vm.Value) (vm.Value, error) {
	return map[string]func(args []vm.Value, env vm.Value) (vm.Value, error){
		"print":   PrintOp,
		"echo":    PrintOp,
		"display": DisplayOp,
		"newline": func(_ []vm.Value, _ vm.Value) (vm.Value, error) { return NewlineOp() },
	}
}
