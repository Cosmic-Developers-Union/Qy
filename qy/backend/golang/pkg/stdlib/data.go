package stdlib

import (
	"strconv"

	"github.com/Cosmic-Developers-Union/Qy/qy/backend/golang/pkg/vm"
)

// `qy.core` 的 chain / 容器 / 谓词算子。
//
// 真源：`qy/std/data.py`（对应 `qy/backend/typescript/src/stdlib/data.ts`）。

func isQyChain(value vm.Value) bool {
	if vm.IsNil(value) {
		return true
	}
	_, ok := value.(*vm.Chain)
	return ok
}

func properChainItems(value vm.Value, context string) ([]vm.Value, error) {
	items, err := vm.ChainToSlice(value)
	if err != nil {
		return nil, vm.NewTypeError(context + " expects a proper Qy chain")
	}
	return items, nil
}

// Atom 是 `atom`：不是非空 chain / tuple 时为真。
func Atom(value vm.Value) vm.Value {
	if vm.IsNil(value) {
		return vm.QyT
	}
	if _, ok := value.(*vm.Chain); ok {
		return vm.QyNil
	}
	if tuple, ok := value.(*vm.TupleValue); ok {
		return boolValue(len(tuple.Items) == 0)
	}
	if items, ok := value.([]vm.Value); ok {
		return boolValue(len(items) == 0)
	}
	return vm.QyT
}

// IsIdentical 是 `is`：identity 比较。
func IsIdentical(left, right vm.Value) vm.Value {
	return boolValue(identityEquals(left, right))
}

// Eq 是 `eq`：Lisp 风格 eq（原子按值、引用类型按 identity 类型检查）。
func Eq(left, right vm.Value) (vm.Value, error) {
	if vm.IsNil(left) && vm.IsNil(right) {
		return vm.QyT, nil
	}
	if vm.IsT(left) && vm.IsT(right) {
		return vm.QyT, nil
	}
	if vm.IsNone(left) && vm.IsNone(right) {
		return vm.QyT, nil
	}
	switch l := left.(type) {
	case *vm.Number:
		if r, ok := right.(*vm.Number); ok && l.TypeName == r.TypeName && l.Val == r.Val {
			return vm.QyT, nil
		}
		// 数值与数值不同 concrete 类型不算 eq（与 TS 的 constructor 检查一致）
		if _, ok := right.(*vm.Number); ok {
			return vm.QyNil, nil
		}
		return vm.QyNil, nil
	case *vm.StringValue:
		if r, ok := right.(*vm.StringValue); ok && l.Value == r.Value {
			return vm.QyT, nil
		}
		return vm.QyNil, nil
	case *vm.Symbol:
		if r, ok := right.(*vm.Symbol); ok && l.Name == r.Name {
			return vm.QyT, nil
		}
		return vm.QyNil, nil
	case string:
		if r, ok := right.(string); ok && l == r {
			return vm.QyT, nil
		}
		return vm.QyNil, nil
	}
	return vm.QyNil, nil
}

// SameQyKey 是容器 key 比较（跨宿主 str / NumberValue 也成立）。
func SameQyKey(left, right vm.Value) bool {
	if l, ok := left.(*vm.StringValue); ok {
		if r, ok := right.(string); ok {
			return l.Value == r
		}
	}
	if l, ok := left.(string); ok {
		if r, ok := right.(*vm.StringValue); ok {
			return l == r.Value
		}
		if r, ok := right.(string); ok {
			return l == r
		}
	}
	if _, isBool := left.(bool); isBool {
		return identityEquals(left, right)
	}
	if _, isBool := right.(bool); isBool {
		return identityEquals(left, right)
	}
	result, err := Eq(left, right)
	if err != nil {
		return false
	}
	return vm.IsT(result)
}

// CarOp 是 `car`。
func CarOp(value vm.Value) (vm.Value, error) {
	if vm.IsNil(value) {
		return vm.QyNil, nil
	}
	if chain, ok := value.(*vm.Chain); ok {
		return chain.Head, nil
	}
	return nil, vm.NewTypeError("car expects a chain")
}

// CdrOp 是 `cdr`。
func CdrOp(value vm.Value) (vm.Value, error) {
	if vm.IsNil(value) {
		return vm.QyNil, nil
	}
	if chain, ok := value.(*vm.Chain); ok {
		return chain.Tail, nil
	}
	return nil, vm.NewTypeError("cdr expects a chain")
}

// ConsOp 是 `cons`。
func ConsOp(head, tail vm.Value) (vm.Value, error) {
	return vm.NewChain(head, tail), nil
}

// ChainOp 是 `chain`：tuple / list → chain。
func ChainOp(value vm.Value) (vm.Value, error) {
	if vm.IsNil(value) {
		return value, nil
	}
	if _, ok := value.(*vm.Chain); ok {
		return value, nil
	}
	if tuple, ok := value.(*vm.TupleValue); ok {
		return vm.SliceToChain(tuple.Items), nil
	}
	if list, ok := value.(*vm.ListValue); ok {
		return vm.SliceToChain(list.Items), nil
	}
	return nil, vm.NewTypeError("chain expects a tuple/list container")
}

func appendItems(value vm.Value) ([]vm.Value, error) {
	if tuple, ok := value.(*vm.TupleValue); ok {
		return tuple.Items, nil
	}
	if list, ok := value.(*vm.ListValue); ok {
		return list.Items, nil
	}
	if vm.IsNil(value) {
		return nil, nil
	}
	if _, ok := value.(*vm.Chain); ok {
		return properChainItems(value, "append")
	}
	return nil, vm.NewTypeError("append expects tuple/list/chain inputs")
}

// AppendOp 是 `append`。
func AppendOp(left, right vm.Value) (vm.Value, error) {
	leftItems, err := appendItems(left)
	if err != nil {
		return nil, err
	}
	rightItems, err := appendItems(right)
	if err != nil {
		return nil, err
	}
	combined := append(append([]vm.Value{}, leftItems...), rightItems...)
	if isQyChain(left) || isQyChain(right) {
		return vm.SliceToChain(combined), nil
	}
	if _, ok := left.(*vm.ListValue); ok {
		return vm.NewList(combined), nil
	}
	if _, ok := right.(*vm.ListValue); ok {
		return vm.NewList(combined), nil
	}
	return vm.NewTuple(combined), nil
}

// LenOp 是 `len`。
func LenOp(value vm.Value) (vm.Value, error) {
	switch v := value.(type) {
	case *vm.Symbol:
		return vm.NewInt(float64(len([]rune(v.Name)))), nil
	case vm.NilValue:
		return vm.NewInt(0), nil
	case *vm.Chain:
		items, err := vm.ChainToSlice(v)
		if err != nil {
			return nil, vm.NewTypeError("len expects a proper Qy chain")
		}
		return vm.NewInt(float64(len(items))), nil
	case *vm.StringValue:
		return vm.NewInt(float64(len([]rune(v.Value)))), nil
	case *vm.TupleValue:
		return vm.NewInt(float64(len(v.Items))), nil
	case *vm.ListValue:
		return vm.NewInt(float64(len(v.Items))), nil
	case *vm.DictValue:
		return vm.NewInt(float64(len(v.Entries))), nil
	case *vm.SetValue:
		return vm.NewInt(float64(len(v.Items))), nil
	}
	return nil, vm.NewTypeError("len expects a collection")
}

func ensureIndex(value vm.Value) (int, error) {
	if number, ok := value.(*vm.Number); ok && number.IsInt {
		return int(number.Val), nil
	}
	if n, ok := value.(int); ok {
		return n, nil
	}
	return 0, vm.NewTypeError("expected integer index")
}

func atIndex(items []vm.Value, index int) vm.Value {
	if index < 0 {
		index += len(items)
	}
	if index < 0 || index >= len(items) {
		return nil
	}
	return items[index]
}

// GetOp 是 `get`：dict / tuple / list / chain 取项。
func GetOp(collection, key vm.Value, defaults ...vm.Value) (vm.Value, error) {
	if len(defaults) > 1 {
		return nil, vm.NewArityError("get expects two or three arguments")
	}
	var fallback vm.Value = vm.QyNone
	if len(defaults) > 0 {
		fallback = defaults[0]
	}
	switch v := collection.(type) {
	case *vm.DictValue:
		for _, entry := range v.Entries {
			if SameQyKey(entry.Key, key) {
				return entry.Value, nil
			}
		}
		return fallback, nil
	case *vm.TupleValue:
		index, err := ensureIndex(key)
		if err != nil {
			return nil, err
		}
		if value := atIndex(v.Items, index); value != nil {
			return value, nil
		}
		return fallback, nil
	case *vm.ListValue:
		index, err := ensureIndex(key)
		if err != nil {
			return nil, err
		}
		if value := atIndex(v.Items, index); value != nil {
			return value, nil
		}
		return fallback, nil
	}
	if vm.IsNil(collection) {
		return fallback, nil
	}
	if _, ok := collection.(*vm.Chain); ok {
		index, err := ensureIndex(key)
		if err != nil {
			return nil, err
		}
		items, err := vm.ChainToSlice(collection)
		if err != nil {
			return nil, err
		}
		if value := atIndex(items, index); value != nil {
			return value, nil
		}
		return fallback, nil
	}
	return nil, vm.NewTypeError("get expects a chain, tuple, list, or dict")
}

// HasOp 是 `has?`。
func HasOp(collection, key vm.Value) (vm.Value, error) {
	switch v := collection.(type) {
	case *vm.DictValue:
		for _, entry := range v.Entries {
			if SameQyKey(entry.Key, key) {
				return vm.QyT, nil
			}
		}
		return vm.QyNil, nil
	case *vm.SetValue:
		for _, item := range v.Items {
			if SameQyKey(item, key) {
				return vm.QyT, nil
			}
		}
		return vm.QyNil, nil
	case *vm.TupleValue:
		index, err := ensureIndex(key)
		if err != nil {
			return nil, err
		}
		return boolValue(index >= -len(v.Items) && index < len(v.Items)), nil
	case *vm.ListValue:
		index, err := ensureIndex(key)
		if err != nil {
			return nil, err
		}
		return boolValue(index >= -len(v.Items) && index < len(v.Items)), nil
	}
	if vm.IsNil(collection) {
		return vm.QyNil, nil
	}
	if _, ok := collection.(*vm.Chain); ok {
		index, err := ensureIndex(key)
		if err != nil {
			return nil, err
		}
		items, err := vm.ChainToSlice(collection)
		if err != nil {
			return nil, err
		}
		return boolValue(index >= -len(items) && index < len(items)), nil
	}
	return nil, vm.NewTypeError("has? expects a chain, tuple, list, dict, or set")
}

// TupleOp 是 `tuple`。
func TupleOp(args ...vm.Value) (vm.Value, error) {
	if len(args) == 1 && isQyChain(args[0]) {
		items, err := properChainItems(args[0], "tuple")
		if err != nil {
			return nil, err
		}
		return vm.NewTuple(items), nil
	}
	return vm.NewTuple(append([]vm.Value{}, args...)), nil
}

// ListOp 是 `list`。
func ListOp(args ...vm.Value) (vm.Value, error) {
	if len(args) == 1 && isQyChain(args[0]) {
		items, err := properChainItems(args[0], "list")
		if err != nil {
			return nil, err
		}
		return vm.NewList(items), nil
	}
	return vm.NewList(append([]vm.Value{}, args...)), nil
}

// DictOp 是 `dict`。
func DictOp(args ...vm.Value) (vm.Value, error) {
	if len(args) == 1 && isQyChain(args[0]) {
		entries := []vm.DictEntry{}
		items, err := properChainItems(args[0], "dict")
		if err != nil {
			return nil, err
		}
		for _, item := range items {
			pair, err := dictEntryPair(item)
			if err != nil {
				return nil, err
			}
			entries = append(entries, pair)
		}
		return vm.NewDict(entries), nil
	}
	if len(args)%2 != 0 {
		return nil, vm.NewArityError("dict expects key/value pairs")
	}
	entries := []vm.DictEntry{}
	for index := 0; index < len(args); index += 2 {
		key := args[index]
		value := args[index+1]
		replaced := false
		for i := range entries {
			if SameQyKey(entries[i].Key, key) {
				entries[i] = vm.DictEntry{Key: key, Value: value}
				replaced = true
				break
			}
		}
		if !replaced {
			entries = append(entries, vm.DictEntry{Key: key, Value: value})
		}
	}
	return vm.NewDict(entries), nil
}

func dictEntryPair(entry vm.Value) (vm.DictEntry, error) {
	if chain, ok := entry.(*vm.Chain); ok {
		if !vm.IsNil(chain.Tail) {
			if _, isChain := chain.Tail.(*vm.Chain); !isChain {
				return vm.DictEntry{Key: chain.Head, Value: chain.Tail}, nil
			}
		}
		items, err := properChainItems(entry, "dict entry")
		if err != nil {
			return vm.DictEntry{}, err
		}
		if len(items) != 2 {
			return vm.DictEntry{}, vm.NewTypeError("dict chain entry must contain two values")
		}
		return vm.DictEntry{Key: items[0], Value: items[1]}, nil
	}
	if items, ok := entry.([]vm.Value); ok {
		if len(items) != 2 {
			return vm.DictEntry{}, vm.NewTypeError("dict chain entry must contain two values")
		}
		return vm.DictEntry{Key: items[0], Value: items[1]}, nil
	}
	return vm.DictEntry{}, vm.NewTypeError("dict chain entry must be a pair")
}

// SetOp 是 `set`。
func SetOp(args ...vm.Value) (vm.Value, error) {
	values := args
	if len(args) == 1 && isQyChain(args[0]) {
		items, err := properChainItems(args[0], "set")
		if err != nil {
			return nil, err
		}
		values = items
	}
	items := []vm.Value{}
	for _, value := range values {
		duplicate := false
		for _, existing := range items {
			if SameQyKey(existing, value) {
				duplicate = true
				break
			}
		}
		if !duplicate {
			items = append(items, value)
		}
	}
	return vm.NewSet(items), nil
}

// TuplePredicate 是 `tuple?`。
func TuplePredicate(value vm.Value) vm.Value {
	_, ok := value.(*vm.TupleValue)
	return boolValue(ok)
}

// ListPredicate 是 `list?`。
func ListPredicate(value vm.Value) vm.Value {
	_, ok := value.(*vm.ListValue)
	return boolValue(ok)
}

// DictPredicate 是 `dict?`。
func DictPredicate(value vm.Value) vm.Value {
	_, ok := value.(*vm.DictValue)
	return boolValue(ok)
}

// SetPredicate 是 `set?`。
func SetPredicate(value vm.Value) vm.Value {
	_, ok := value.(*vm.SetValue)
	return boolValue(ok)
}

// TypeOp 是 `type`：Qy 语义类型名（不泄漏宿主类名）。
func TypeOp(value vm.Value) vm.Value {
	switch value.(type) {
	case vm.NilValue:
		return vm.NewSymbol("nil")
	case vm.TValue:
		return vm.NewSymbol("T")
	case vm.NoneValue:
		return vm.NewSymbol("none")
	case *vm.Chain:
		return vm.NewSymbol("chain")
	case *vm.Symbol:
		return vm.NewSymbol("symbol")
	case *vm.TupleValue:
		return vm.NewSymbol("tuple")
	case *vm.ListValue:
		return vm.NewSymbol("list")
	case *vm.DictValue:
		return vm.NewSymbol("dict")
	case *vm.SetValue:
		return vm.NewSymbol("set")
	case *vm.Number:
		return vm.NewSymbol("number")
	case *vm.StringValue:
		return vm.NewSymbol("string")
	case *vm.CharValue:
		return vm.NewSymbol("char")
	}
	return vm.NewSymbol("object")
}

// ReifyOp 是 `reify`：runtime 值 → syntax datum。
//
// 这是 ScopeOperator（`_reify(args, env)`），所以由 RawOperator 承载。
func ReifyOp(args []vm.Value, _ vm.Value) (vm.Value, error) {
	if len(args) != 1 {
		return nil, vm.NewReifyError("reify expects exactly 1 argument")
	}
	return ReifyValue(args[0])
}

// ReifyValue 是单个值的 reify（含 chain 递归）。
func ReifyValue(value vm.Value) (vm.Value, error) {
	switch v := value.(type) {
	case vm.NilValue:
		return vm.NewSymbol("nil"), nil
	case vm.TValue:
		return vm.NewSymbol("T"), nil
	case vm.NoneValue:
		return vm.NewSymbol("none"), nil
	case *vm.Symbol:
		return v, nil
	case *vm.Number:
		return vm.NewSymbol(strconv.FormatFloat(v.Val, 'f', -1, 64)), nil
	case int:
		return vm.NewSymbol(strconv.Itoa(v)), nil
	case float64:
		return vm.NewSymbol(strconv.FormatFloat(v, 'f', -1, 64)), nil
	case *vm.StringValue:
		return vm.NewSymbol("\"" + v.Value + "\""), nil
	case string:
		return vm.NewSymbol("\"" + v + "\""), nil
	case *vm.CharValue:
		return vm.NewSymbol("#\\" + v.Value), nil
	case *vm.Chain:
		items := []vm.Value{}
		var node vm.Value = v
		for {
			chain, ok := node.(*vm.Chain)
			if !ok {
				break
			}
			reified, err := ReifyValue(chain.Head)
			if err != nil {
				return nil, err
			}
			items = append(items, reified)
			node = chain.Tail
		}
		if vm.IsNil(node) {
			return vm.SliceToChain(items), nil
		}
		tail, err := ReifyValue(node)
		if err != nil {
			return nil, err
		}
		if _, ok := tail.(*vm.Chain); ok || vm.IsNil(tail) {
			tailItems, err := vm.ChainToSlice(tail)
			if err != nil {
				return nil, err
			}
			return vm.SliceToChain(append(append([]vm.Value{}, items...), tailItems...)), nil
		}
		var head vm.Value = vm.QyNil
		if len(items) > 0 {
			head = vm.SliceToChain(items)
		}
		return vm.NewChain(head, tail), nil
	}
	return nil, vm.NewReifyError("cannot reify value of type " + typeNameOf(value))
}

// NormalizeArgument 是 APPLY / `apply` 的实参归一：
// 字面量拼写（Symbol）在 VM 里还原为字面量值（`data.py`）。
func NormalizeArgument(value vm.Value) vm.Value {
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

// DataBindings 返回 `data.py` 的 chain / container 算子绑定。
func DataBindings() map[string]func(args []vm.Value) (vm.Value, error) {
	return map[string]func(args []vm.Value) (vm.Value, error){
		"atom":  func(args []vm.Value) (vm.Value, error) { return Atom(argAt(args, 0)), nil },
		"car":   func(args []vm.Value) (vm.Value, error) { return CarOp(argAt(args, 0)) },
		"cdr":   func(args []vm.Value) (vm.Value, error) { return CdrOp(argAt(args, 0)) },
		"chain": func(args []vm.Value) (vm.Value, error) { return ChainOp(argAt(args, 0)) },
		"append": func(args []vm.Value) (vm.Value, error) {
			return AppendOp(argAt(args, 0), argAt(args, 1))
		},
		"cons": func(args []vm.Value) (vm.Value, error) { return ConsOp(argAt(args, 0), argAt(args, 1)) },
		"eq":   func(args []vm.Value) (vm.Value, error) { return Eq(argAt(args, 0), argAt(args, 1)) },
		"get": func(args []vm.Value) (vm.Value, error) {
			return GetOp(argAt(args, 0), argAt(args, 1), args[minInt(2, len(args)):]...)
		},
		"has?":  func(args []vm.Value) (vm.Value, error) { return HasOp(argAt(args, 0), argAt(args, 1)) },
		"is":    func(args []vm.Value) (vm.Value, error) { return IsIdentical(argAt(args, 0), argAt(args, 1)), nil },
		"len":   func(args []vm.Value) (vm.Value, error) { return LenOp(argAt(args, 0)) },
		"type":  func(args []vm.Value) (vm.Value, error) { return TypeOp(argAt(args, 0)), nil },
		"tuple": func(args []vm.Value) (vm.Value, error) { return TupleOp(args...) },
		"tuple?": func(args []vm.Value) (vm.Value, error) {
			return TuplePredicate(argAt(args, 0)), nil
		},
		"list": func(args []vm.Value) (vm.Value, error) { return ListOp(args...) },
		"list?": func(args []vm.Value) (vm.Value, error) {
			return ListPredicate(argAt(args, 0)), nil
		},
		"dict": func(args []vm.Value) (vm.Value, error) { return DictOp(args...) },
		"dict?": func(args []vm.Value) (vm.Value, error) {
			return DictPredicate(argAt(args, 0)), nil
		},
		"set": func(args []vm.Value) (vm.Value, error) { return SetOp(args...) },
		"set?": func(args []vm.Value) (vm.Value, error) {
			return SetPredicate(argAt(args, 0)), nil
		},
	}
}

func minInt(a, b int) int {
	if a < b {
		return a
	}
	return b
}

func boolValue(value bool) vm.Value {
	if value {
		return vm.QyT
	}
	return vm.QyNil
}
