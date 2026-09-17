package stdlib

import (
	"math"

	"github.com/Cosmic-Developers-Union/Qy/qy/backend/golang/pkg/vm"
)

// number-ss 的算术 / 比较算子。
//
// 真源：`qy/session/number_ops.py`。核心约束（必须有，否则语料语义会变）：
//
//  1. 不做隐式提升：所有参数必须是同一个 concrete `NumberValue` 类型，
//     否则触发 `unsupported-operation` effect（`number_ops._ensure_same_number_type`）；
//  2. 除零触发 `divide-by-zero`（`/` 可恢复，`mod` 不可恢复）；
//  3. 定宽整型 / 浮点越界触发 `numeric-overflow`；
//  4. 整数除法向零截断（不是 Python `//` 的向下取整）；
//  5. `=` 是同 concrete 类型的数值相等；两侧非数值时退化为 identity 比较；
//  6. `==` 是宿主 `==` 语义（`_py_eq`）。

// integerBounds 是定宽整型的取值范围；IntValue（任意精度）不在表中。
var integerBounds = map[string][2]float64{
	vm.NumberTypeInt8:   {-128, 127},
	vm.NumberTypeInt16:  {-32768, 32767},
	vm.NumberTypeInt32:  {-2147483648, 2147483647},
	vm.NumberTypeInt64:  {-9223372036854775808, 9223372036854775807},
	vm.NumberTypeUInt8:  {0, 255},
	vm.NumberTypeUInt16: {0, 65535},
	vm.NumberTypeUInt32: {0, 4294967295},
	vm.NumberTypeUInt64: {0, 18446744073709551615},
}

// CoerceHostNumber 把宿主 int / float 升格为 Qy 语义数值（`_coerce_host_number`）。
func CoerceHostNumber(value vm.Value) vm.Value {
	switch v := value.(type) {
	case *vm.Number:
		return v
	case bool:
		return v
	case int:
		return vm.NewInt(float64(v))
	case int64:
		return vm.NewInt(float64(v))
	case float64:
		if v == math.Trunc(v) && !math.IsInf(v, 0) {
			return vm.NewInt(v)
		}
		return vm.NewFloat(v)
	}
	return value
}

func typeNameOf(value vm.Value) string {
	switch v := value.(type) {
	case *vm.Number:
		return v.TypeName
	case nil:
		return "NoneType"
	case bool:
		return "bool"
	case int, int64, float64:
		return "int"
	case string:
		return "str"
	case *vm.Symbol:
		return "Symbol"
	case *vm.StringValue:
		return "StringValue"
	case vm.NilValue:
		return "nil"
	case vm.TValue:
		return "T"
	case vm.NoneValue:
		return "none"
	}
	return "object"
}

// ensureSameNumberType 要求所有参数是同一个 concrete number 类型
// （`_ensure_same_number_type`）。
func ensureSameNumberType(args []vm.Value, op string) (*vm.Number, error) {
	if len(args) == 0 {
		return nil, vm.NewTypeError(op + " requires at least one argument")
	}
	head, ok := args[0].(*vm.Number)
	if !ok {
		return nil, vm.NewTypeError(op + " expects a number, got " + typeNameOf(args[0]))
	}
	for index := 1; index < len(args); index++ {
		arg, isNumber := args[index].(*vm.Number)
		if !isNumber || arg.TypeName != head.TypeName {
			payload := vm.NewDict([]vm.DictEntry{
				{Key: vm.NewSymbol("operator"), Value: vm.NewString(op)},
				{Key: vm.NewSymbol("left_type"), Value: vm.NewString(head.TypeName)},
				{Key: vm.NewSymbol("right_type"), Value: vm.NewString(typeNameOf(args[index]))},
				{Key: vm.NewSymbol("argument_index"), Value: vm.NewInt(float64(index))},
			})
			return nil, vm.PerformEffect("unsupported-operation", payload, false)
		}
	}
	return head, nil
}

func checkIntegerRange(value float64, typeName, op string) (float64, error) {
	bounds, ok := integerBounds[typeName]
	if !ok {
		return value, nil
	}
	minimum, maximum := bounds[0], bounds[1]
	if value < minimum || value > maximum {
		payload := vm.NewDict([]vm.DictEntry{
			{Key: vm.NewSymbol("type"), Value: vm.NewString(typeName)},
			{Key: vm.NewSymbol("operation"), Value: vm.NewString(op)},
			{Key: vm.NewSymbol("result"), Value: vm.NewInt(value)},
			{Key: vm.NewSymbol("min"), Value: vm.NewInt(minimum)},
			{Key: vm.NewSymbol("max"), Value: vm.NewInt(maximum)},
		})
		return value, vm.PerformEffect("numeric-overflow", payload, false)
	}
	return value, nil
}

func checkFloatFinite(value float64, typeName, op string) (float64, error) {
	if math.IsNaN(value) || math.IsInf(value, 0) {
		payload := vm.NewDict([]vm.DictEntry{
			{Key: vm.NewSymbol("type"), Value: vm.NewString(typeName)},
			{Key: vm.NewSymbol("operation"), Value: vm.NewString(op)},
			{Key: vm.NewSymbol("result"), Value: vm.NewFloat(value)},
		})
		return value, vm.PerformEffect("numeric-overflow", payload, false)
	}
	return value, nil
}

type numberKernel func(typeName string, args []*vm.Number) (*vm.Number, error)

func dispatchOp(op string, rawArgs []vm.Value, integerKernel, floatKernel numberKernel) (vm.Value, error) {
	coerced := make([]vm.Value, 0, len(rawArgs))
	for _, arg := range rawArgs {
		coerced = append(coerced, CoerceHostNumber(arg))
	}
	valueType, err := ensureSameNumberType(coerced, op)
	if err != nil {
		return nil, err
	}
	typed := make([]*vm.Number, 0, len(coerced))
	for _, item := range coerced {
		if number, ok := item.(*vm.Number); ok {
			typed = append(typed, number)
		}
	}
	if valueType.IsInt {
		return integerKernel(valueType.TypeName, typed)
	}
	return floatKernel(valueType.TypeName, typed)
}

// -- 整数内核 ---------------------------------------------------------------

func integerAdd(typeName string, args []*vm.Number) (*vm.Number, error) {
	total := 0.0
	for _, arg := range args {
		total += arg.Val
	}
	checked, err := checkIntegerRange(total, typeName, "+")
	if err != nil {
		return nil, err
	}
	return vm.NewNumberOfType(typeName, checked), nil
}

func integerSub(typeName string, args []*vm.Number) (*vm.Number, error) {
	if len(args) == 1 {
		checked, err := checkIntegerRange(-args[0].Val, typeName, "-")
		if err != nil {
			return nil, err
		}
		return vm.NewNumberOfType(typeName, checked), nil
	}
	result := args[0].Val
	for _, arg := range args[1:] {
		result -= arg.Val
	}
	checked, err := checkIntegerRange(result, typeName, "-")
	if err != nil {
		return nil, err
	}
	return vm.NewNumberOfType(typeName, checked), nil
}

func integerMul(typeName string, args []*vm.Number) (*vm.Number, error) {
	result := 1.0
	for _, arg := range args {
		result *= arg.Val
	}
	checked, err := checkIntegerRange(result, typeName, "*")
	if err != nil {
		return nil, err
	}
	return vm.NewNumberOfType(typeName, checked), nil
}

// truncDiv 是向零截断的整数除法（number_ops._integer_div：`int(a / b)`）。
func truncDiv(a, b float64) float64 {
	return math.Trunc(a / b)
}

func integerDiv(typeName string, args []*vm.Number) (*vm.Number, error) {
	payload := vm.NewDict([]vm.DictEntry{{Key: vm.NewSymbol("operator"), Value: vm.NewString("/")}})
	if len(args) == 1 {
		first := args[0].Val
		if first == 0 {
			return nil, vm.PerformEffect("divide-by-zero", payload, true)
		}
		checked, err := checkIntegerRange(truncDiv(1, first), typeName, "/")
		if err != nil {
			return nil, err
		}
		return vm.NewNumberOfType(typeName, checked), nil
	}
	result := args[0].Val
	for _, arg := range args[1:] {
		divisor := arg.Val
		if divisor == 0 {
			return nil, vm.PerformEffect("divide-by-zero", payload, true)
		}
		result = truncDiv(result, divisor)
	}
	checked, err := checkIntegerRange(result, typeName, "/")
	if err != nil {
		return nil, err
	}
	return vm.NewNumberOfType(typeName, checked), nil
}

// pyMod 是 Python 的 `%`（结果符号跟随除数）。
func pyMod(a, b float64) float64 {
	result := math.Mod(a, b)
	if result != 0 && (result < 0) != (b < 0) {
		return result + b
	}
	return result
}

func integerMod(typeName string, args []*vm.Number) (*vm.Number, error) {
	if len(args) != 2 {
		return nil, vm.NewTypeError("mod expects exactly 2 arguments")
	}
	a, b := args[0].Val, args[1].Val
	if b == 0 {
		payload := vm.NewDict([]vm.DictEntry{{Key: vm.NewSymbol("operator"), Value: vm.NewString("mod")}})
		return nil, vm.PerformEffect("divide-by-zero", payload, false)
	}
	checked, err := checkIntegerRange(pyMod(a, b), typeName, "mod")
	if err != nil {
		return nil, err
	}
	return vm.NewNumberOfType(typeName, checked), nil
}

// -- 浮点内核 ---------------------------------------------------------------

func floatAdd(typeName string, args []*vm.Number) (*vm.Number, error) {
	total := 0.0
	for _, arg := range args {
		total += arg.Val
	}
	checked, err := checkFloatFinite(total, typeName, "+")
	if err != nil {
		return nil, err
	}
	return vm.NewNumberOfType(typeName, checked), nil
}

func floatSub(typeName string, args []*vm.Number) (*vm.Number, error) {
	if len(args) == 1 {
		return vm.NewNumberOfType(typeName, -args[0].Val), nil
	}
	result := args[0].Val
	for _, arg := range args[1:] {
		result -= arg.Val
	}
	checked, err := checkFloatFinite(result, typeName, "-")
	if err != nil {
		return nil, err
	}
	return vm.NewNumberOfType(typeName, checked), nil
}

func floatMul(typeName string, args []*vm.Number) (*vm.Number, error) {
	result := 1.0
	for _, arg := range args {
		result *= arg.Val
	}
	checked, err := checkFloatFinite(result, typeName, "*")
	if err != nil {
		return nil, err
	}
	return vm.NewNumberOfType(typeName, checked), nil
}

func floatDiv(typeName string, args []*vm.Number) (*vm.Number, error) {
	payload := vm.NewDict([]vm.DictEntry{{Key: vm.NewSymbol("operator"), Value: vm.NewString("/")}})
	if len(args) == 1 {
		first := args[0].Val
		if first == 0 {
			return nil, vm.PerformEffect("divide-by-zero", payload, true)
		}
		checked, err := checkFloatFinite(1/first, typeName, "/")
		if err != nil {
			return nil, err
		}
		return vm.NewNumberOfType(typeName, checked), nil
	}
	result := args[0].Val
	for _, arg := range args[1:] {
		divisor := arg.Val
		if divisor == 0 {
			return nil, vm.PerformEffect("divide-by-zero", payload, true)
		}
		result /= divisor
	}
	checked, err := checkFloatFinite(result, typeName, "/")
	if err != nil {
		return nil, err
	}
	return vm.NewNumberOfType(typeName, checked), nil
}

func floatMod(typeName string, args []*vm.Number) (*vm.Number, error) {
	if len(args) != 2 {
		return nil, vm.NewTypeError("mod expects exactly 2 arguments")
	}
	a, b := args[0].Val, args[1].Val
	if b == 0 {
		payload := vm.NewDict([]vm.DictEntry{{Key: vm.NewSymbol("operator"), Value: vm.NewString("mod")}})
		return nil, vm.PerformEffect("divide-by-zero", payload, false)
	}
	checked, err := checkFloatFinite(a-b*math.Trunc(a/b), typeName, "mod")
	if err != nil {
		return nil, err
	}
	return vm.NewNumberOfType(typeName, checked), nil
}

// -- 公开算子 ---------------------------------------------------------------

// Add 是 `+`。
func Add(args ...vm.Value) (vm.Value, error) {
	return dispatchOp("+", args, integerAdd, floatAdd)
}

// Sub 是 `-`。
func Sub(args ...vm.Value) (vm.Value, error) {
	return dispatchOp("-", args, integerSub, floatSub)
}

// Mul 是 `*`。
func Mul(args ...vm.Value) (vm.Value, error) {
	return dispatchOp("*", args, integerMul, floatMul)
}

// Div 是 `/`。
func Div(args ...vm.Value) (vm.Value, error) {
	return dispatchOp("/", args, integerDiv, floatDiv)
}

// Mod 是 `mod`。
func Mod(args ...vm.Value) (vm.Value, error) {
	return dispatchOp("mod", args, integerMod, floatMod)
}

func ordering(op string, args []vm.Value, compare func(a, b float64) bool) (vm.Value, error) {
	if len(args) != 2 {
		return nil, vm.NewTypeError(op + " expects exactly 2 arguments")
	}
	coerced := []vm.Value{CoerceHostNumber(args[0]), CoerceHostNumber(args[1])}
	if _, err := ensureSameNumberType(coerced, op); err != nil {
		return nil, err
	}
	left, leftOK := coerced[0].(*vm.Number)
	right, rightOK := coerced[1].(*vm.Number)
	if !leftOK || !rightOK {
		return nil, vm.NewTypeError(op + " expects numbers")
	}
	if compare(left.Val, right.Val) {
		return vm.QyT, nil
	}
	return vm.QyNil, nil
}

// Lt 是 `<`。
func Lt(args ...vm.Value) (vm.Value, error) {
	return ordering("<", args, func(a, b float64) bool { return a < b })
}

// Gt 是 `>`。
func Gt(args ...vm.Value) (vm.Value, error) {
	return ordering(">", args, func(a, b float64) bool { return a > b })
}

// Le 是 `<=`。
func Le(args ...vm.Value) (vm.Value, error) {
	return ordering("<=", args, func(a, b float64) bool { return a <= b })
}

// Ge 是 `>=`。
func Ge(args ...vm.Value) (vm.Value, error) {
	return ordering(">=", args, func(a, b float64) bool { return a >= b })
}

// identityEquals 是安全的宿主 identity 比较（Go 的 `==` 对 slice 会 panic）。
func identityEquals(left, right vm.Value) bool {
	if left == nil || right == nil {
		return left == nil && right == nil
	}
	switch left.(type) {
	case []vm.Value, []int:
		return false
	}
	switch right.(type) {
	case []vm.Value, []int:
		return false
	}
	return left == right
}

// NumEq 是 `=`：同 concrete 数值类型相等；非数值退化为 identity（number_ops._num_eq）。
func NumEq(left, right vm.Value) (vm.Value, error) {
	if _, ok := left.(bool); ok {
		return boolResult(identityEquals(left, right)), nil
	}
	if _, ok := right.(bool); ok {
		return boolResult(identityEquals(left, right)), nil
	}
	a := CoerceHostNumber(left)
	b := CoerceHostNumber(right)
	numberA, aIsNumber := a.(*vm.Number)
	numberB, bIsNumber := b.(*vm.Number)
	if aIsNumber && bIsNumber {
		if numberA.TypeName != numberB.TypeName {
			payload := vm.NewDict([]vm.DictEntry{
				{Key: vm.NewSymbol("operator"), Value: vm.NewString("=")},
				{Key: vm.NewSymbol("left_type"), Value: vm.NewString(numberA.TypeName)},
				{Key: vm.NewSymbol("right_type"), Value: vm.NewString(numberB.TypeName)},
			})
			return nil, vm.PerformEffect("unsupported-operation", payload, false)
		}
		return boolResult(numberA.Val == numberB.Val), nil
	}
	return boolResult(identityEquals(left, right)), nil
}

// PyEq 是 `==`：宿主 `==` 语义（number_ops._py_eq）。
func PyEq(left, right vm.Value) (vm.Value, error) {
	return boolResult(pyEquals(left, right)), nil
}

// PyEquals 是 Python `==` 的近似实现。
//
// 覆盖语料需要的几类：数值按值、StringValue 按值、Symbol 按名字（dataclass
// 结构相等）、nil/T/none 单例、容器按元素。
func PyEquals(left, right vm.Value) bool { return pyEquals(left, right) }

func pyEquals(left, right vm.Value) bool {
	if identityEquals(left, right) {
		return true
	}
	switch l := left.(type) {
	case *vm.Number:
		if r, ok := right.(*vm.Number); ok {
			return l.Val == r.Val
		}
	case *vm.StringValue:
		if r, ok := right.(*vm.StringValue); ok {
			return l.Value == r.Value
		}
	case *vm.Symbol:
		if r, ok := right.(*vm.Symbol); ok {
			return l.Name == r.Name
		}
	case []vm.Value:
		if r, ok := right.([]vm.Value); ok {
			if len(l) != len(r) {
				return false
			}
			for index := range l {
				if !pyEquals(l[index], r[index]) {
					return false
				}
			}
			return true
		}
	}
	return false
}

func boolResult(value bool) vm.Value {
	if value {
		return vm.QyT
	}
	return vm.QyNil
}
