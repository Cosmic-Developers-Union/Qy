// Package bytecode 装载 `qy export` 产出的字节码 JSON 交换格式。
//
// 契约真源：`qy/backend/vm/bytecode.py::serialize_bytecode_json`（编码）与
// `load_bytecode_json`（解码）。本包只负责 JSON 层的结构还原；操作数的
// 语义值解码在 `pkg/vm` 完成（decode.go），以避免 bytecode → vm 的循环依赖。
package bytecode

import (
	"encoding/json"
	"fmt"
)

// Program 是一份字节码程序。
type Program struct {
	Version   int        `json:"version"`
	Main      int        `json:"main"`
	Functions []Function `json:"functions"`

	// HygieneBindings 是卫生宏别名 → 原始符号名。
	//
	// 编译期程序的 hygiene 别名在宏展开时已作为真实隐藏绑定写入 env；从 JSON
	// 装载的程序没有这一步，必须按该字段补上，否则卫生宏产物运行期报
	// `unresolved symbol '__qy_hygiene_def___N'`。
	HygieneBindings map[string]string `json:"hygiene_bindings,omitempty"`

	// ModuleMacroExports 是模块名 → 编译期宏导出名列表。
	//
	// 运行期这些名字没有绑定值，`from` 命中它们时应跳过绑定而不是报错。
	ModuleMacroExports map[string][]string `json:"module_macro_exports,omitempty"`
}

// Function 是一个字节码函数。
type Function struct {
	Name          string        `json:"name"`
	Params        []string      `json:"params"`
	RegisterCount int           `json:"register_count"`
	Instructions  []Instruction `json:"instructions"`
}

// Instruction 是一条指令。Operands 已按操作数对象还原（Type / Class / Value）。
type Instruction struct {
	Opcode   string    `json:"opcode"`
	Operands []Operand `json:"operands"`
}

// Operand 是一个操作数。
//
// JSON 形状为 `{"type": <kind>, "class": <semantic class>, "value": <payload>}`；
// `class` 只在载荷是 Qy 语义值时出现（例如 `{"type":"int","class":"IntValue",...}`）。
type Operand struct {
	Type  string
	Class string
	Value interface{}
}

// UnmarshalJSON 实现通用操作数解码：value 保留为通用 JSON 值
// （数字为 float64、对象为 map[string]interface{}、数组为 []interface{}）。
func (o *Operand) UnmarshalJSON(data []byte) error {
	var raw struct {
		Type  string          `json:"type"`
		Class string          `json:"class"`
		Value json.RawMessage `json:"value"`
	}
	if err := json.Unmarshal(data, &raw); err != nil {
		return fmt.Errorf("decode operand: %w", err)
	}
	o.Type = raw.Type
	o.Class = raw.Class
	o.Value = nil
	if len(raw.Value) > 0 {
		var value interface{}
		if err := json.Unmarshal(raw.Value, &value); err != nil {
			return fmt.Errorf("decode operand value: %w", err)
		}
		o.Value = value
	}
	return nil
}

// AsInt 把操作数载荷还原为整数。
func (o *Operand) AsInt() int { return AsInt(o.Value) }

// AsString 把操作数载荷还原为字符串。
func (o *Operand) AsString() string {
	if s, ok := o.Value.(string); ok {
		return s
	}
	return ""
}

// AsBool 把操作数载荷还原为布尔。
func (o *Operand) AsBool() bool {
	switch v := o.Value.(type) {
	case bool:
		return v
	case float64:
		return v != 0
	}
	return false
}

// AsIntList 把操作数载荷还原为整数数组（reg_tuple / 整数数组）。
func (o *Operand) AsIntList() []int {
	items, ok := o.Value.([]interface{})
	if !ok {
		return nil
	}
	result := make([]int, 0, len(items))
	for _, item := range items {
		result = append(result, AsInt(item))
	}
	return result
}

// AsStringList 把操作数载荷还原为字符串数组（symbol_tuple）。
func (o *Operand) AsStringList() []string {
	items, ok := o.Value.([]interface{})
	if !ok {
		return nil
	}
	result := make([]string, 0, len(items))
	for _, item := range items {
		result = append(result, fmt.Sprintf("%v", item))
	}
	return result
}

// HandlerSpec 是 handler_specs 里的一项。
type HandlerSpec struct {
	Effect    string `json:"effect"`
	HandlerFn int    `json:"handler_fn"`
}

// AsHandlerSpecs 还原 handler_specs。
func (o *Operand) AsHandlerSpecs() []HandlerSpec {
	items, ok := o.Value.([]interface{})
	if !ok {
		return nil
	}
	specs := make([]HandlerSpec, 0, len(items))
	for _, item := range items {
		entry, ok := item.(map[string]interface{})
		if !ok {
			continue
		}
		effect, _ := entry["effect"].(string)
		specs = append(specs, HandlerSpec{Effect: effect, HandlerFn: AsInt(entry["handler_fn"])})
	}
	return specs
}

// ImportSpec 是 import_specs 里的一项。
type ImportSpec struct {
	Name  string `json:"name"`
	Alias string `json:"alias"`
}

// AsImportSpecs 还原 import_specs。
func (o *Operand) AsImportSpecs() []ImportSpec {
	items, ok := o.Value.([]interface{})
	if !ok {
		return nil
	}
	specs := make([]ImportSpec, 0, len(items))
	for _, item := range items {
		entry, ok := item.(map[string]interface{})
		if !ok {
			continue
		}
		name, _ := entry["name"].(string)
		alias, _ := entry["alias"].(string)
		specs = append(specs, ImportSpec{Name: name, Alias: alias})
	}
	return specs
}

// AsInt 把通用 JSON 值还原为整数（对应 TS `asInt`）。
func AsInt(value interface{}) int {
	switch v := value.(type) {
	case bool:
		if v {
			return 1
		}
		return 0
	case float64:
		return int(v)
	case int:
		return v
	case int64:
		return int(v)
	case string:
		var parsed int
		if _, err := fmt.Sscanf(v, "%d", &parsed); err == nil {
			return parsed
		}
	}
	return 0
}
