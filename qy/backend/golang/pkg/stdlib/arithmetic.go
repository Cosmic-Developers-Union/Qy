package stdlib

import (
	"math"
	"math/big"

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
//  4. 整数运算是任意精度（Python `IntValue` 是 int），定宽整型才做范围检查；
//  5. 二元整数除法：异号且余数非零时 Python 走 `int(a / b)` 的 **float 路径**
//     （`_integer_div`），必须逐字节复刻；单参数 `/` 用 `1 // first`（floor）；
//  6. `mod` 用 Python floor 语义（结果符号跟随除数）；
//  7. `=` 是同 concrete 类型的数值相等；两侧非数值时退化为 identity 比较；
//  8. `==` 是宿主 `==` 语义（`_py_eq`）。

// integerBounds 是定宽整型的取值范围（任意精度表示）；IntValue（任意精度）不在表中。
var integerBounds = map[string][2]*big.Int{
	vm.NumberTypeInt8:   {big.NewInt(-128), big.NewInt(127)},
	vm.NumberTypeInt16:  {big.NewInt(-32768), big.NewInt(32767)},
	vm.NumberTypeInt32:  {big.NewInt(-2147483648), big.NewInt(2147483647)},
	vm.NumberTypeInt64:  {mustBigInt("-9223372036854775808"), mustBigInt("9223372036854775807")},
	vm.NumberTypeUInt8:  {big.NewInt(0), big.NewInt(255)},
	vm.NumberTypeUInt16: {big.NewInt(0), big.NewInt(65535)},
	vm.NumberTypeUInt32: {big.NewInt(0), big.NewInt(4294967295)},
	vm.NumberTypeUInt64: {big.NewInt(0), mustBigInt("18446744073709551615")},
}

// mustBigInt 只用于本文件的常量表。
func mustBigInt(text string) *big.Int {
	value, ok := new(big.Int).SetString(text, 10)
	if !ok {
		panic("invalid integer bound: " + text)
	}
	return value
}

// CoerceHostNumber 把宿主 int / float 升格为 Qy 语义数值（`_coerce_host_number`）。
func CoerceHostNumber(value vm.Value) vm.Value {
	switch v := value.(type) {
	case *vm.Number:
		return v
	case bool:
		return v
	case int:
		return vm.NewInt(int64(v))
	case int64:
		return vm.NewInt(v)
	case *big.Int:
		return vm.NewBigInt(v)
	case float64:
		if v == math.Trunc(v) && !math.IsInf(v, 0) {
			// 整数值的宿主浮点按精确整数升格，避免 >2^53 丢精度。
			if integer, _ := new(big.Float).SetFloat64(v).Int(nil); integer != nil {
				return vm.NewBigInt(integer)
			}
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
	case int, int64, float64, *big.Int:
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
				{Key: vm.NewSymbol("argument_index"), Value: vm.NewInt(int64(index))},
			})
			return nil, vm.PerformEffect("unsupported-operation", payload, false)
		}
	}
	return head, nil
}

// checkIntegerRange 是定宽整型越界检查（`_check_integer_range`）；
// IntValue（任意精度）不在 integerBounds 中，不做检查。
func checkIntegerRange(value *big.Int, typeName, op string) (*big.Int, error) {
	bounds, ok := integerBounds[typeName]
	if !ok {
		return value, nil
	}
	minimum, maximum := bounds[0], bounds[1]
	if value.Cmp(minimum) < 0 || value.Cmp(maximum) > 0 {
		payload := vm.NewDict([]vm.DictEntry{
			{Key: vm.NewSymbol("type"), Value: vm.NewString(typeName)},
			{Key: vm.NewSymbol("operation"), Value: vm.NewString(op)},
			{Key: vm.NewSymbol("result"), Value: vm.NewBigInt(value)},
			{Key: vm.NewSymbol("min"), Value: vm.NewBigInt(minimum)},
			{Key: vm.NewSymbol("max"), Value: vm.NewBigInt(maximum)},
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

type integerKernel func(typeName string, args []*vm.Number) (*vm.Number, error)
type floatKernel func(typeName string, args []*vm.Number) (*vm.Number, error)

func dispatchOp(op string, rawArgs []vm.Value, integer integerKernel, float floatKernel) (vm.Value, error) {
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
		return integer(valueType.TypeName, typed)
	}
	return float(valueType.TypeName, typed)
}

// -- 整数内核（全部 big.Int，任意精度） ---------------------------------------

func integerAdd(typeName string, args []*vm.Number) (*vm.Number, error) {
	total := big.NewInt(0)
	for _, arg := range args {
		total.Add(total, arg.BigPayload())
	}
	checked, err := checkIntegerRange(total, typeName, "+")
	if err != nil {
		return nil, err
	}
	return vm.NewIntegerOfType(typeName, checked), nil
}

func integerSub(typeName string, args []*vm.Number) (*vm.Number, error) {
	if len(args) == 1 {
		negated := new(big.Int).Neg(args[0].BigPayload())
		checked, err := checkIntegerRange(negated, typeName, "-")
		if err != nil {
			return nil, err
		}
		return vm.NewIntegerOfType(typeName, checked), nil
	}
	result := new(big.Int).Set(args[0].BigPayload())
	for _, arg := range args[1:] {
		result.Sub(result, arg.BigPayload())
	}
	checked, err := checkIntegerRange(result, typeName, "-")
	if err != nil {
		return nil, err
	}
	return vm.NewIntegerOfType(typeName, checked), nil
}

func integerMul(typeName string, args []*vm.Number) (*vm.Number, error) {
	result := big.NewInt(1)
	for _, arg := range args {
		result.Mul(result, arg.BigPayload())
	}
	checked, err := checkIntegerRange(result, typeName, "*")
	if err != nil {
		return nil, err
	}
	return vm.NewIntegerOfType(typeName, checked), nil
}

// floorDiv 是 Python `//`（向负无穷取整）。big.Int 的 Quo 向零截断，需要修正。
func floorDiv(a, b *big.Int) *big.Int {
	quotient := new(big.Int).Quo(a, b)
	remainder := new(big.Int).Rem(a, b)
	if remainder.Sign() != 0 && (remainder.Sign() < 0) != (b.Sign() < 0) {
		quotient.Sub(quotient, big.NewInt(1))
	}
	return quotient
}

// truncDivViaFloat 复刻 Python 二元整数除法里的 `int(result / divisor)`。
//
// `_integer_div` 在"异号且余数非零"时走的是 **float 真除法**再截断，所以超大
// 整数会因此丢精度（Python 侧宿主缺陷）。为了与 Python 逐字节一致，这里同样
// 走 double：big.Int→float64 与 CPython 的 int→double 都是正确舍入，
// `math.Trunc` 与 `int()` 都是向零截断。CPython 在 float 溢出时抛 OverflowError，
// 这里返回运行时错误。
func truncDivViaFloat(a, b *big.Int) (*big.Int, error) {
	left, _ := new(big.Float).SetInt(a).Float64()
	right, _ := new(big.Float).SetInt(b).Float64()
	if math.IsInf(left, 0) || math.IsNaN(left) || math.IsInf(right, 0) || math.IsNaN(right) {
		return nil, vm.NewRuntimeError("integer division overflow")
	}
	truncated := math.Trunc(left / right)
	if math.IsInf(truncated, 0) || math.IsNaN(truncated) {
		return nil, vm.NewRuntimeError("integer division overflow")
	}
	result, _ := new(big.Float).SetFloat64(truncated).Int(nil)
	if result == nil {
		return nil, vm.NewRuntimeError("integer division overflow")
	}
	return result, nil
}

func integerDiv(typeName string, args []*vm.Number) (*vm.Number, error) {
	payload := vm.NewDict([]vm.DictEntry{{Key: vm.NewSymbol("operator"), Value: vm.NewString("/")}})
	if len(args) == 1 {
		first := args[0].BigPayload()
		if first.Sign() == 0 {
			return nil, vm.PerformEffect("divide-by-zero", payload, true)
		}
		// 注意：Python `_integer_div` 的单参数分支是 `1 // first`（floor），
		// 与二元分支的向零截断不同。见 qy/session/number_ops.py:244-249。
		checked, err := checkIntegerRange(floorDiv(big.NewInt(1), first), typeName, "/")
		if err != nil {
			return nil, err
		}
		return vm.NewIntegerOfType(typeName, checked), nil
	}
	result := new(big.Int).Set(args[0].BigPayload())
	for _, arg := range args[1:] {
		divisor := arg.BigPayload()
		if divisor.Sign() == 0 {
			return nil, vm.PerformEffect("divide-by-zero", payload, true)
		}
		signsDiffer := (result.Sign() < 0) != (divisor.Sign() < 0)
		remainder := new(big.Int).Rem(result, divisor)
		if signsDiffer && remainder.Sign() != 0 {
			// 逐字复刻 Python：异号且余数非零 → `int(result / divisor)`（float）。
			quotient, err := truncDivViaFloat(result, divisor)
			if err != nil {
				return nil, err
			}
			result = quotient
			continue
		}
		// 其余情形 `result // divisor` 与向零截断等价（同号，或整除）。
		result.Quo(result, divisor)
	}
	checked, err := checkIntegerRange(result, typeName, "/")
	if err != nil {
		return nil, err
	}
	return vm.NewIntegerOfType(typeName, checked), nil
}

// pyMod 是 Python 的 `%`（结果符号跟随除数）。big.Int Rem 的符号跟随被除数，
// 需要修正。
func pyMod(a, b *big.Int) *big.Int {
	result := new(big.Int).Rem(a, b)
	if result.Sign() != 0 && (result.Sign() < 0) != (b.Sign() < 0) {
		result.Add(result, b)
	}
	return result
}

func integerMod(typeName string, args []*vm.Number) (*vm.Number, error) {
	if len(args) != 2 {
		return nil, vm.NewTypeError("mod expects exactly 2 arguments")
	}
	a, b := args[0].BigPayload(), args[1].BigPayload()
	if b.Sign() == 0 {
		payload := vm.NewDict([]vm.DictEntry{{Key: vm.NewSymbol("operator"), Value: vm.NewString("mod")}})
		return nil, vm.PerformEffect("divide-by-zero", payload, false)
	}
	checked, err := checkIntegerRange(pyMod(a, b), typeName, "mod")
	if err != nil {
		return nil, err
	}
	return vm.NewIntegerOfType(typeName, checked), nil
}

// -- 浮点内核 ---------------------------------------------------------------

func floatAdd(typeName string, args []*vm.Number) (*vm.Number, error) {
	total := 0.0
	for _, arg := range args {
		total += arg.FloatPayload()
	}
	checked, err := checkFloatFinite(total, typeName, "+")
	if err != nil {
		return nil, err
	}
	return vm.NewFloatOfType(typeName, checked), nil
}

func floatSub(typeName string, args []*vm.Number) (*vm.Number, error) {
	if len(args) == 1 {
		return vm.NewFloatOfType(typeName, -args[0].FloatPayload()), nil
	}
	result := args[0].FloatPayload()
	for _, arg := range args[1:] {
		result -= arg.FloatPayload()
	}
	checked, err := checkFloatFinite(result, typeName, "-")
	if err != nil {
		return nil, err
	}
	return vm.NewFloatOfType(typeName, checked), nil
}

func floatMul(typeName string, args []*vm.Number) (*vm.Number, error) {
	result := 1.0
	for _, arg := range args {
		result *= arg.FloatPayload()
	}
	checked, err := checkFloatFinite(result, typeName, "*")
	if err != nil {
		return nil, err
	}
	return vm.NewFloatOfType(typeName, checked), nil
}

func floatDiv(typeName string, args []*vm.Number) (*vm.Number, error) {
	payload := vm.NewDict([]vm.DictEntry{{Key: vm.NewSymbol("operator"), Value: vm.NewString("/")}})
	if len(args) == 1 {
		first := args[0].FloatPayload()
		if first == 0 {
			return nil, vm.PerformEffect("divide-by-zero", payload, true)
		}
		checked, err := checkFloatFinite(1/first, typeName, "/")
		if err != nil {
			return nil, err
		}
		return vm.NewFloatOfType(typeName, checked), nil
	}
	result := args[0].FloatPayload()
	for _, arg := range args[1:] {
		divisor := arg.FloatPayload()
		if divisor == 0 {
			return nil, vm.PerformEffect("divide-by-zero", payload, true)
		}
		result /= divisor
	}
	checked, err := checkFloatFinite(result, typeName, "/")
	if err != nil {
		return nil, err
	}
	return vm.NewFloatOfType(typeName, checked), nil
}

func floatMod(typeName string, args []*vm.Number) (*vm.Number, error) {
	if len(args) != 2 {
		return nil, vm.NewTypeError("mod expects exactly 2 arguments")
	}
	a, b := args[0].FloatPayload(), args[1].FloatPayload()
	if b == 0 {
		payload := vm.NewDict([]vm.DictEntry{{Key: vm.NewSymbol("operator"), Value: vm.NewString("mod")}})
		return nil, vm.PerformEffect("divide-by-zero", payload, false)
	}
	checked, err := checkFloatFinite(a-b*math.Trunc(a/b), typeName, "mod")
	if err != nil {
		return nil, err
	}
	return vm.NewFloatOfType(typeName, checked), nil
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

// compareNumbers 返回 -1 / 0 / 1（同 concrete 类型下的精确比较）。
func compareNumbers(left, right *vm.Number) int {
	if left.IsInt && right.IsInt {
		return left.BigPayload().Cmp(right.BigPayload())
	}
	a, b := left.FloatPayload(), right.FloatPayload()
	switch {
	case a < b:
		return -1
	case a > b:
		return 1
	}
	return 0
}

func ordering(op string, args []vm.Value, accept func(comparison int) bool) (vm.Value, error) {
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
	if accept(compareNumbers(left, right)) {
		return vm.QyT, nil
	}
	return vm.QyNil, nil
}

// Lt 是 `<`。
func Lt(args ...vm.Value) (vm.Value, error) {
	return ordering("<", args, func(comparison int) bool { return comparison < 0 })
}

// Gt 是 `>`。
func Gt(args ...vm.Value) (vm.Value, error) {
	return ordering(">", args, func(comparison int) bool { return comparison > 0 })
}

// Le 是 `<=`。
func Le(args ...vm.Value) (vm.Value, error) {
	return ordering("<=", args, func(comparison int) bool { return comparison <= 0 })
}

// Ge 是 `>=`。
func Ge(args ...vm.Value) (vm.Value, error) {
	return ordering(">=", args, func(comparison int) bool { return comparison >= 0 })
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
		return boolResult(numberA.NumberEquals(numberB)), nil
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
			return l.NumberEquals(r)
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
