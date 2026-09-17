package vm

import "math/big"

// Qy 运行时值模型。
//
// 真源：
//   - `qy/core/syntax.py`（Symbol / Chain / nil / T / none）
//   - `qy/sem/core.py`（Value / NumberValue / StringValue / 容器）
//
// 这是 TypeScript 宿主 `qy/backend/typescript/src/values.ts` 的 Go 同构移植：
// 值类型一一对应，语义点也保持一致。
//
// 关键语义点：
//   - nil / T / none 是单例值，不是宿主 bool / nil；
//   - 数值带 "concrete type" 身份（`(+ int32 int64)` 不隐式提升，
//     `=` 要求两侧 concrete number 类型相同，见 `qy/session/number_ops.py`）；
//   - Symbol 不做 interning：`=` 对非数值退化为 identity，`eq` 对 Symbol 做结构比较。

// Value 是任意 Qy 运行时值（宿主原语只作为过渡期互操作出现）。
type Value = interface{}

// ---------------------------------------------------------------------------
// 单例值
// ---------------------------------------------------------------------------

// NilValue 对应 Python `qy.core.syntax.nil`（空链）。
type NilValue struct{}

// TValue 对应 Python `qy.core.syntax.T`。
type TValue struct{}

// NoneValue 对应 Python `qy.core.syntax.NONE`。
type NoneValue struct{}

var (
	// QyNil 是 nil 单例。
	QyNil Value = NilValue{}
	// QyT 是真值单例。
	QyT Value = TValue{}
	// QyNone 是 none 单例。
	QyNone Value = NoneValue{}
)

// IsNil 判断是否为 nil 单例。
func IsNil(v Value) bool { _, ok := v.(NilValue); return ok }

// IsT 判断是否为 T 单例。
func IsT(v Value) bool { _, ok := v.(TValue); return ok }

// IsNone 判断是否为 none 单例。
func IsNone(v Value) bool { _, ok := v.(NoneValue); return ok }

// ---------------------------------------------------------------------------
// symbol / chain
// ---------------------------------------------------------------------------

// Symbol 是 Qy 语法 datum 的原子：一个符号拼写。对应 `qy.core.syntax.Symbol`。
type Symbol struct {
	Name string
}

// NewSymbol 构造一个 symbol。
func NewSymbol(name string) *Symbol { return &Symbol{Name: name} }

// Chain 是不可变 cons cell。对应 `qy.core.syntax.Chain`。
type Chain struct {
	Head Value
	Tail Value
}

// NewChain 构造一个 cons cell。
func NewChain(head, tail Value) *Chain { return &Chain{Head: head, Tail: tail} }

// ---------------------------------------------------------------------------
// 数值值
// ---------------------------------------------------------------------------

// concrete number 类型名。对应 `qy/backend/vm/bytecode.py` 里的
// IntValue / Int8Value / ... / FloatValue 系列类名。
const (
	NumberTypeInt      = "int"
	NumberTypeInt8     = "int8"
	NumberTypeInt16    = "int16"
	NumberTypeInt32    = "int32"
	NumberTypeInt64    = "int64"
	NumberTypeUInt8    = "uint8"
	NumberTypeUInt16   = "uint16"
	NumberTypeUInt32   = "uint32"
	NumberTypeUInt64   = "uint64"
	NumberTypeFloat    = "float"
	NumberTypeFloat16  = "float16"
	NumberTypeFloat32  = "float32"
	NumberTypeFloat128 = "float128"
	NumberTypeComplex  = "complex"
	NumberTypeRational = "rational"
)

// Number 是数值家族的统一表示。对应 `qy.sem.core.NumberValue` 及其子类。
//
// TypeName 承担 TS 里 `constructor` 的身份角色：`=` / `+` 要求两侧 TypeName 相同。
//
// 载荷精度：整型家族（IsInt == true）的载荷是 `*big.Int`，与 Python
// `IntValue.value` 的任意精度 int 一致（`qy/sem/core.py::IntValue`）；浮点家族
// 才用 float64。**绝不允许**把整型载荷退回 float64 —— 2^53 之后会静默丢精度。
type Number struct {
	TypeName string
	IsInt    bool
	// Int 是整型家族的精确载荷（IsInt 为 true 时非 nil）。
	Int *big.Int
	// Float 是浮点家族的载荷（IsInt 为 false 时有效）。
	Float float64
}

// NewInt 构造 IntValue（任意精度整型）。参数是 int64 以兼容宿主内建常量。
func NewInt(v int64) *Number { return NewBigInt(big.NewInt(v)) }

// NewBigInt 用任意精度载荷构造 IntValue。
func NewBigInt(v *big.Int) *Number {
	return &Number{TypeName: NumberTypeInt, IsInt: true, Int: new(big.Int).Set(v)}
}

// NewIntegerOfType 按 concrete 类型名构造整型数值（int32 / uint8 / ...）。
func NewIntegerOfType(typeName string, v *big.Int) *Number {
	return &Number{TypeName: typeName, IsInt: true, Int: new(big.Int).Set(v)}
}

// NewFloat 构造 FloatValue。
func NewFloat(v float64) *Number {
	return &Number{TypeName: NumberTypeFloat, IsInt: false, Float: v}
}

// NewFloatOfType 按 concrete 类型名构造浮点数值（float16 / float32 / float128）。
func NewFloatOfType(typeName string, v float64) *Number {
	return &Number{TypeName: typeName, IsInt: false, Float: v}
}

// BigPayload 返回整型载荷（调用方需保证 IsInt）。
func (n *Number) BigPayload() *big.Int { return n.Int }

// FloatPayload 返回浮点载荷（调用方需保证 !IsInt）。
func (n *Number) FloatPayload() float64 { return n.Float }

// String 对应 Python `str(NumberValue)`：整数纯十进制，浮点走 repr 规则。
func (n *Number) String() string {
	if n.IsInt {
		return n.Int.String()
	}
	return PyFloatRepr(n.Float)
}

// NumberEquals 是同 concrete 类型下的数值相等（载荷按精确值比较）。
func (n *Number) NumberEquals(other *Number) bool {
	if n.IsInt && other.IsInt {
		return n.Int.Cmp(other.Int) == 0
	}
	if !n.IsInt && !other.IsInt {
		return n.Float == other.Float
	}
	return false
}

// isIntegerNumberType 判断 concrete 类型是否属于整型家族。
func isIntegerNumberType(typeName string) bool {
	switch typeName {
	case NumberTypeInt, NumberTypeInt8, NumberTypeInt16, NumberTypeInt32, NumberTypeInt64,
		NumberTypeUInt8, NumberTypeUInt16, NumberTypeUInt32, NumberTypeUInt64:
		return true
	}
	return false
}

// ---------------------------------------------------------------------------
// 字符串 / 字符 / 容器
// ---------------------------------------------------------------------------

// CharValue 是单字符值。对应 `qy.sem.core.CharValue`。
type CharValue struct {
	Value string
}

// NewChar 构造字符值。
func NewChar(v string) *CharValue { return &CharValue{Value: v} }

// StringValue 是 Qy 字符串值。对应 `qy.sem.core.StringValue`。
type StringValue struct {
	Value string
}

// NewString 构造字符串值。
func NewString(v string) *StringValue { return &StringValue{Value: v} }

// TupleValue 是不可变 tuple。对应 `qy.sem.core.TupleValue`。
type TupleValue struct {
	Items []Value
}

// NewTuple 构造 tuple。
func NewTuple(items []Value) *TupleValue { return &TupleValue{Items: items} }

// ListValue 是 Qy list。对应 `qy.sem.core.ListValue`。
type ListValue struct {
	Items []Value
}

// NewList 构造 list。
func NewList(items []Value) *ListValue { return &ListValue{Items: items} }

// DictEntry 是 dict 的一个有序 entry。
type DictEntry struct {
	Key   Value
	Value Value
}

// DictValue 是 Qy dict（有序 entry）。
type DictValue struct {
	Entries []DictEntry
}

// NewDict 构造 dict。
func NewDict(entries []DictEntry) *DictValue { return &DictValue{Entries: entries} }

// SetValue 是 Qy set（有序去重项）。
type SetValue struct {
	Items []Value
}

// NewSet 构造 set。
func NewSet(items []Value) *SetValue { return &SetValue{Items: items} }

// ---------------------------------------------------------------------------
// 可调用值 / effect / module
// ---------------------------------------------------------------------------

// PureOperator 是 eager 参数算子值（对应 Python PureOperator）。
type PureOperator struct {
	Name string
	Fn   func(args []Value) (Value, error)
}

// RawOperator 是 raw 参数算子值（对应 Python Scope/Control/Effect/MetaOperator）。
type RawOperator struct {
	Name string
	Fn   func(args []Value, env Value) (Value, error)
}

// FunctionValue 是可调用的字节码函数值（闭包）。
//
// 对应 `qy/vm/bytecode.py::BytecodeFunctionValue`；`<main>` / `<module-body>`
// 直接复用闭包空间，其余函数调用新建子空间（见 machine.go::makeFrame）。
type FunctionValue struct {
	Fn      *BytecodeFunction
	Closure *Env
}

// EffectDefinition 是 effect 定义值。对应 `qy/sem/runtime.py::EffectDefinition`。
type EffectDefinition struct {
	Name      string
	Resumable bool
}

// Continuation 是续延值。对应 `qy/vm/instance/frame.py::QyContinuation`。
//
// ResumeFn 是恢复快照的闭包（TS 版用同样的闭包设计），返回恢复后的结果值。
type Continuation struct {
	Effect    string
	Resumable bool
	ResumeFn  func(value Value) (Value, error)
}

// ModuleValue 是模块值。对应 `qy/import_/module.py::StandardModule`。
type ModuleValue struct {
	Name         string
	Exports      map[string]Value
	MacroExports map[string]Value
}

// NewModuleValue 构造模块值（macro exports 默认为空）。
func NewModuleValue(name string, exports map[string]Value) *ModuleValue {
	if exports == nil {
		exports = map[string]Value{}
	}
	return &ModuleValue{Name: name, Exports: exports, MacroExports: map[string]Value{}}
}

// Resolve 按运行时导出 → 宏导出顺序解析模块内名字。
func (m *ModuleValue) Resolve(name string) (Value, bool) {
	if v, ok := m.Exports[name]; ok {
		return v, true
	}
	v, ok := m.MacroExports[name]
	return v, ok
}

// compileTimeMacroType 是 MAKE_MACRO 的编译期占位符类型。
// 对应 Python 的 `_COMPILE_TIME_MACRO`：它不进入 APPEND_RESULT / RETURN 的结果。
type compileTimeMacroType struct{}

// CompileTimeMacro 是编译期宏占位符单例。
var CompileTimeMacro Value = compileTimeMacroType{}

// IsCompileTimeMacro 判断是否为编译期宏占位符。
func IsCompileTimeMacro(v Value) bool {
	_, ok := v.(compileTimeMacroType)
	return ok
}

// HandlerRecord 是一条 HANDLER_PUSH 记录。
type HandlerRecord struct {
	HandlerID int
	Target    int
	ParentID  *int
	Specs     []HandlerSpec
}

// ---------------------------------------------------------------------------
// chain 工具函数（对应 qy.core.syntax 的 car/cdr/cons/chain_to_list/list_to_chain）
// ---------------------------------------------------------------------------

// CarOf 返回 chain 的 head。
func CarOf(v Value) (Value, error) {
	if c, ok := v.(*Chain); ok {
		return c.Head, nil
	}
	return nil, NewTypeError("car expects a Chain, got " + Describe(v))
}

// CdrOf 返回 chain 的 tail。
func CdrOf(v Value) (Value, error) {
	if c, ok := v.(*Chain); ok {
		return c.Tail, nil
	}
	return nil, NewTypeError("cdr expects a Chain, got " + Describe(v))
}

// ChainToSlice 把 proper chain 转成切片；improper chain 报错。
func ChainToSlice(v Value) ([]Value, error) {
	if IsNil(v) {
		return nil, nil
	}
	result := []Value{}
	current := v
	for {
		c, ok := current.(*Chain)
		if !ok {
			break
		}
		result = append(result, c.Head)
		current = c.Tail
	}
	if !IsNil(current) {
		return nil, NewTypeError("Cannot convert improper chain to list")
	}
	return result, nil
}

// SliceToChain 把切片转成 proper chain。
func SliceToChain(items []Value) Value {
	var result Value = QyNil
	for i := len(items) - 1; i >= 0; i-- {
		result = NewChain(items[i], result)
	}
	return result
}

// ChainValueToSlice 是 ChainToSlice 的宽松版本：nil → 空切片，其余非 chain 原样返回单项。
func ChainValueToSlice(v Value) []Value {
	if IsNil(v) {
		return nil
	}
	if c, ok := v.(*Chain); ok {
		_ = c
		items, err := ChainToSlice(v)
		if err != nil {
			return nil
		}
		return items
	}
	return []Value{v}
}

// DefaultLiteralType 返回 symbol 拼写对应的字面量类型名；不是字面量时返回 ""。
func DefaultLiteralType(name string) string {
	if isStringLiteral(name) {
		return "string"
	}
	if isCharLiteral(name) {
		if _, ok := parseCharLiteral(name); ok {
			return "char"
		}
		return ""
	}
	value, ok := tryDefaultLiteral(name)
	if !ok {
		return ""
	}
	switch v := value.(type) {
	case NilValue:
		return "nil"
	case TValue:
		return "T"
	case NoneValue:
		return "none"
	case *Number:
		_ = v
		return "number"
	}
	return ""
}
