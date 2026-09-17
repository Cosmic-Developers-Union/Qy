package vm

import (
	"encoding/json"
	"math/big"

	"github.com/Cosmic-Developers-Union/Qy/qy/backend/golang/pkg/bytecode"
)

// 字节码 JSON → VM 内部结构（含语义值）的解码。
//
// 对应 `qy/backend/typescript/src/bytecode.ts` 的 decodeValue / decodeOperand，
// 但分成了两步：`pkg/bytecode` 只做 JSON 结构还原，本文件把操作数还原成 Qy 值。

// BytecodeFunction 是 VM 内部使用的函数表示（操作数已解码）。
type BytecodeFunction struct {
	Name          string
	Params        []string
	RegisterCount int
	Instructions  []Instruction
}

// Instruction 是一条已解码指令。
type Instruction struct {
	Opcode   string
	Operands []Value
}

// HandlerSpec 是 handler 规格：effect 名 + handler 函数下标。
type HandlerSpec struct {
	Effect    string
	HandlerFn int
}

// ImportSpec 是 from-import 规格：原名 + 别名。
type ImportSpec struct {
	Name  string
	Alias string
}

// semanticNumberTypes 把 JSON 里的语义类名映射为 concrete number 类型名。
var semanticNumberTypes = map[string]string{
	"IntValue":      NumberTypeInt,
	"Int8Value":     NumberTypeInt8,
	"Int16Value":    NumberTypeInt16,
	"Int32Value":    NumberTypeInt32,
	"Int64Value":    NumberTypeInt64,
	"UInt8Value":    NumberTypeUInt8,
	"UInt16Value":   NumberTypeUInt16,
	"UInt32Value":   NumberTypeUInt32,
	"UInt64Value":   NumberTypeUInt64,
	"FloatValue":    NumberTypeFloat,
	"Float16Value":  NumberTypeFloat16,
	"Float32Value":  NumberTypeFloat32,
	"Float128Value": NumberTypeFloat128,
}

// decodeFunctions 把装载的程序解码为 VM 内部函数表。
func decodeFunctions(prog *bytecode.Program) ([]*BytecodeFunction, error) {
	functions := make([]*BytecodeFunction, 0, len(prog.Functions))
	for i := range prog.Functions {
		raw := &prog.Functions[i]
		fn := &BytecodeFunction{
			Name:          raw.Name,
			Params:        append([]string{}, raw.Params...),
			RegisterCount: raw.RegisterCount,
			Instructions:  make([]Instruction, 0, len(raw.Instructions)),
		}
		for j := range raw.Instructions {
			rawInstr := &raw.Instructions[j]
			operands := make([]Value, 0, len(rawInstr.Operands))
			for k := range rawInstr.Operands {
				value, err := decodeOperand(&rawInstr.Operands[k])
				if err != nil {
					return nil, err
				}
				operands = append(operands, value)
			}
			fn.Instructions = append(fn.Instructions, Instruction{
				Opcode:   rawInstr.Opcode,
				Operands: operands,
			})
		}
		functions = append(functions, fn)
	}
	return functions, nil
}

// decodeOperand 解码单个操作数：`reg` → int，其余走 decodeValue。
func decodeOperand(op *bytecode.Operand) (Value, error) {
	if op.Class != "" {
		if value, ok := decodeSemanticValue(op); ok {
			return value, nil
		}
	}
	switch op.Type {
	case "reg":
		return bytecode.AsInt(op.Value), nil
	case "nil":
		return QyNil, nil
	case "t":
		return QyT, nil
	case "none":
		return QyNone, nil
	case "int":
		// 精确解析：整数字面量可能超过 int64（Python int 任意精度）。能装进
		// int64 的（寄存器下标 / 函数下标）返回 int，超出的返回 *big.Int。
		if number, ok := op.Value.(json.Number); ok {
			if parsed, err := number.Int64(); err == nil {
				return int(parsed), nil
			}
			return bytecode.ExactBigInt(op.Value), nil
		}
		return bytecode.AsInt(op.Value), nil
	case "float":
		return op.AsFloat(), nil
	case "bool":
		return op.AsBool(), nil
	case "string":
		return op.AsString(), nil
	case "symbol":
		return NewSymbol(op.AsString()), nil
	case "chain":
		return decodeChainPayload(op.Value), nil
	case "binding_addr":
		// abstract-machine 方言：SLOT_COMPLETE 的 (space, slot) 地址。
		address, _ := op.AsBindingAddr()
		return address, nil
	case "effect_def":
		entry, _ := op.Value.(map[string]interface{})
		name, _ := entry["name"].(string)
		resumable := true
		if raw, ok := entry["resumable"].(bool); ok {
			resumable = raw
		}
		return &EffectDefinition{Name: name, Resumable: resumable}, nil
	case "list":
		return decodeValueArray(op.Value), nil
	case "tuple":
		return decodeValueArray(op.Value), nil
	case "reg_tuple":
		return op.AsIntList(), nil
	case "symbol_tuple":
		symbols := []*Symbol{}
		for _, name := range op.AsStringList() {
			symbols = append(symbols, NewSymbol(name))
		}
		return symbols, nil
	case "handler_specs":
		specs := []HandlerSpec{}
		for _, spec := range op.AsHandlerSpecs() {
			specs = append(specs, HandlerSpec{Effect: spec.Effect, HandlerFn: spec.HandlerFn})
		}
		return specs, nil
	case "import_specs":
		specs := []ImportSpec{}
		for _, spec := range op.AsImportSpecs() {
			specs = append(specs, ImportSpec{Name: spec.Name, Alias: spec.Alias})
		}
		return specs, nil
	case "unknown":
		return nil, NewRuntimeError("bytecode JSON contains an unencodable value")
	default:
		return op.Value, nil
	}
}

// decodeValueArray 解码 `[{type,value}, ...]` 形状的数组载荷。
func decodeValueArray(payload interface{}) []Value {
	items, ok := payload.([]interface{})
	if !ok {
		return []Value{}
	}
	result := make([]Value, 0, len(items))
	for _, item := range items {
		result = append(result, decodeValue(item))
	}
	return result
}

// decodeValue 解码嵌套的语义值载荷（对应 TS `decodeValue`）。
func decodeValue(payload interface{}) Value {
	if payload == nil {
		return nil
	}
	entry, ok := payload.(map[string]interface{})
	if !ok {
		// 裸标量（数字 / 字符串 / 布尔）保持宿主标量语义
		return payload
	}
	op := &bytecode.Operand{}
	if kind, ok := entry["type"].(string); ok {
		op.Type = kind
	}
	if class, ok := entry["class"].(string); ok {
		op.Class = class
	}
	op.Value = entry["value"]
	value, err := decodeOperand(op)
	if err != nil {
		return nil
	}
	return value
}

// decodeSemanticValue 处理带 `class` 的载荷（对应 TS `decodeSemanticValue`）。
//
// 形状：`{"type": ..., "class": "IntValue", "value": {"value": <operand>}}`。
func decodeSemanticValue(op *bytecode.Operand) (Value, bool) {
	entry, ok := op.Value.(map[string]interface{})
	if !ok {
		return nil, false
	}
	field := func(name string) Value { return decodeValue(entry[name]) }
	numberValue := func(typeName string) Value {
		// 数值语义载荷形状：`{"value": {"type": "int", "value": <精确 token>}}`。
		// 整型必须走 ExactBigInt：任何经 float64 的路径都会在 2^53 之后丢精度。
		payload := entry["value"]
		if isIntegerNumberType(typeName) {
			return NewIntegerOfType(typeName, exactIntegerPayload(payload))
		}
		return NewFloatOfType(typeName, exactFloatPayload(payload))
	}

	if typeName, ok := semanticNumberTypes[op.Class]; ok {
		return numberValue(typeName), true
	}
	switch op.Class {
	case "StringValue":
		return NewString(stringFromValue(field("value"))), true
	case "CharValue":
		return NewChar(stringFromValue(field("value"))), true
	case "TupleValue":
		return NewTuple(valueSlice(field("items"))), true
	case "ListValue":
		return NewList(valueSlice(field("items"))), true
	case "SetValue":
		return NewSet(valueSlice(field("items"))), true
	case "DictValue", "HashMapValue":
		return NewDict(dictEntries(field("entries"))), true
	case "ArrayValue":
		return NewList(valueSlice(field("items"))), true
	case "ComplexValue":
		return NewFloat(0), true
	case "RationalValue":
		return NewInt(0), true
	}
	return nil, false
}

// exactIntegerPayload 从数值语义载荷里精确取出整数（绝不经过 float64）。
func exactIntegerPayload(raw interface{}) *big.Int {
	if wrapper, ok := raw.(map[string]interface{}); ok {
		raw = wrapper["value"]
	}
	return bytecode.ExactBigInt(raw)
}

// exactFloatPayload 从数值语义载荷里取出浮点。
func exactFloatPayload(raw interface{}) float64 {
	if wrapper, ok := raw.(map[string]interface{}); ok {
		raw = wrapper["value"]
	}
	op := &bytecode.Operand{Value: raw}
	return op.AsFloat()
}

func stringFromValue(value Value) string {
	switch v := value.(type) {
	case string:
		return v
	case *StringValue:
		return v.Value
	case *Symbol:
		return v.Name
	case nil:
		return ""
	}
	return ""
}

func valueSlice(value Value) []Value {
	items, ok := value.([]interface{})
	if !ok {
		if typed, isTyped := value.([]Value); isTyped {
			return typed
		}
		return []Value{}
	}
	result := make([]Value, 0, len(items))
	for _, item := range items {
		result = append(result, decodeValue(item))
	}
	return result
}

func dictEntries(value Value) []DictEntry {
	items, ok := value.([]interface{})
	if !ok {
		return nil
	}
	entries := make([]DictEntry, 0, len(items))
	for _, item := range items {
		pair, isPair := item.([]interface{})
		if !isPair || len(pair) != 2 {
			entries = append(entries, DictEntry{Key: decodeValue(item), Value: QyNil})
			continue
		}
		entries = append(entries, DictEntry{Key: decodeValue(pair[0]), Value: decodeValue(pair[1])})
	}
	return entries
}

// decodeChainPayload 解码 `{head, tail}` 递归的 chain 载荷（null 结尾表示 nil）。
func decodeChainPayload(payload interface{}) Value {
	if payload == nil {
		return QyNil
	}
	node, ok := payload.(map[string]interface{})
	if !ok {
		return decodeValue(payload)
	}
	head := decodeValue(node["head"])
	tail := decodeChainPayload(node["tail"])
	return NewChain(head, tail)
}
