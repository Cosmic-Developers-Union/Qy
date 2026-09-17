package stdlib

import (
	"math/big"
	"testing"

	"github.com/Cosmic-Developers-Union/Qy/qy/backend/golang/pkg/vm"
)

// 大整数（任意精度）单元测试。
//
// 对应 Python：
//   - `qy/sem/core.py::IntValue`（任意精度 int）
//   - `qy/session/number_ops.py`（定宽范围检查、同 concrete 类型约束、除法 float 路径）

func bigInt(t *testing.T, text string) *big.Int {
	t.Helper()
	value, ok := new(big.Int).SetString(text, 10)
	if !ok {
		t.Fatalf("bad big integer literal %q", text)
	}
	return value
}

// bigValue 构造任意精度 IntValue。
func bigValue(t *testing.T, text string) vm.Value {
	t.Helper()
	return vm.NewBigInt(bigInt(t, text))
}

// eval 执行算子并返回格式化结果；出错则测试失败。
func eval(t *testing.T, call func() (vm.Value, error)) string {
	t.Helper()
	value, err := call()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	return vm.FormatValue(value)
}

// effectOf 触发 effect 时返回信号；没有触发返回 nil。
func effectOf(t *testing.T, run func() (vm.Value, error)) *vm.EffectSignal {
	t.Helper()
	_, err := run()
	if err == nil {
		return nil
	}
	signal, ok := err.(*vm.EffectSignal)
	if !ok {
		t.Fatalf("error = %T (%v), want *vm.EffectSignal", err, err)
	}
	return signal
}

func TestBigIntAddMulSub(t *testing.T) {
	if got := eval(t, func() (vm.Value, error) {
		return Add(bigValue(t, "9007199254740993"), vm.NewInt(1))
	}); got != "9007199254740994" {
		t.Fatalf("(+ 2^53 1) = %s", got)
	}

	if got := eval(t, func() (vm.Value, error) {
		return Mul(bigValue(t, "9007199254740993"), bigValue(t, "9007199254740993"))
	}); got != "81129638414606699710187514626049" {
		t.Fatalf("(* 2^53 2^53) = %s", got)
	}

	if got := eval(t, func() (vm.Value, error) {
		return Sub(vm.NewInt(0), bigValue(t, "9007199254740993"))
	}); got != "-9007199254740993" {
		t.Fatalf("(- 0 2^53) = %s", got)
	}
}

func TestBigIntCompareAndEquality(t *testing.T) {
	if got := eval(t, func() (vm.Value, error) {
		return Lt(bigValue(t, "100000000000000000000"), bigValue(t, "100000000000000000001"))
	}); got != "T" {
		t.Fatalf("(< a b) = %s", got)
	}
	if got := eval(t, func() (vm.Value, error) {
		return NumEq(bigValue(t, "9007199254740993"), bigValue(t, "9007199254740993"))
	}); got != "T" {
		t.Fatalf("(= a a) = %s", got)
	}
	if got := eval(t, func() (vm.Value, error) {
		return Le(bigValue(t, "9007199254740993"), bigValue(t, "9007199254740993"))
	}); got != "T" {
		t.Fatalf("(<= a a) = %s", got)
	}
}

func TestBigIntModuloAndDivision(t *testing.T) {
	if got := eval(t, func() (vm.Value, error) {
		return Mod(bigValue(t, "100000000000000000000000000007"), vm.NewInt(97))
	}); got != "64" {
		t.Fatalf("(mod big 97) = %s", got)
	}
	if got := eval(t, func() (vm.Value, error) { return Mod(vm.NewInt(-7), vm.NewInt(3)) }); got != "2" {
		t.Fatalf("(mod -7 3) = %s", got)
	}
	if got := eval(t, func() (vm.Value, error) { return Mod(vm.NewInt(7), vm.NewInt(-3)) }); got != "-2" {
		t.Fatalf("(mod 7 -3) = %s", got)
	}
	if got := eval(t, func() (vm.Value, error) { return Div(vm.NewInt(7), vm.NewInt(2)) }); got != "3" {
		t.Fatalf("(/ 7 2) = %s", got)
	}
	if got := eval(t, func() (vm.Value, error) { return Div(vm.NewInt(-7), vm.NewInt(2)) }); got != "-3" {
		t.Fatalf("(/ -7 2) = %s", got)
	}
	// 单参数 `/` 在 Python `_integer_div` 里用 `1 // first`（floor），不是截断。
	if got := eval(t, func() (vm.Value, error) { return Div(vm.NewInt(-2)) }); got != "-1" {
		t.Fatalf("(/ -2) = %s", got)
	}
	// 异号且余数非零时 Python 走 `int(result / divisor)`（float 除法），
	// 超大字面量会丢精度；结果必须逐字节一致。
	if got := eval(t, func() (vm.Value, error) {
		return Div(bigValue(t, "-100000000000000000000"), vm.NewInt(7))
	}); got != "-14285714285714286592" {
		t.Fatalf("(/ -1e20 7) = %s", got)
	}
}

func TestBigIntFixedWidthOverflow(t *testing.T) {
	signal := effectOf(t, func() (vm.Value, error) {
		return Add(
			vm.NewIntegerOfType(vm.NumberTypeInt32, big.NewInt(2147483647)),
			vm.NewIntegerOfType(vm.NumberTypeInt32, big.NewInt(1)),
		)
	})
	if signal == nil || signal.Effect != "numeric-overflow" {
		t.Fatalf("int32 overflow signal = %+v", signal)
	}
	signal = effectOf(t, func() (vm.Value, error) {
		return Sub(
			vm.NewIntegerOfType(vm.NumberTypeUInt8, big.NewInt(0)),
			vm.NewIntegerOfType(vm.NumberTypeUInt8, big.NewInt(1)),
		)
	})
	if signal == nil || signal.Effect != "numeric-overflow" {
		t.Fatalf("uint8 underflow signal = %+v", signal)
	}
}

func TestBigIntMixedTypeIsUnsupported(t *testing.T) {
	signal := effectOf(t, func() (vm.Value, error) {
		return Add(bigValue(t, "9007199254740993"), vm.NewFloat(1.5))
	})
	if signal == nil || signal.Effect != "unsupported-operation" {
		t.Fatalf("mixed int/float signal = %+v", signal)
	}
}

func TestBigIntReifySpelling(t *testing.T) {
	symbol, err := ReifyValue(bigValue(t, "9007199254740993"))
	if err != nil {
		t.Fatalf("ReifyValue: %v", err)
	}
	if got := vm.FormatValue(symbol); got != "9007199254740993" {
		t.Fatalf("reify big = %s", got)
	}
}
