// Package bytecode 装载 `qy export` 产出的字节码 JSON 交换格式。
//
// 契约真源：`qy/backend/vm/bytecode.py::serialize_bytecode_json`（编码）与
// `load_bytecode_json`（解码）。本包只负责 JSON 层的结构还原；操作数的
// 语义值解码在 `pkg/vm` 完成（decode.go），以避免 bytecode → vm 的循环依赖。
package bytecode

import (
	"bytes"
	"encoding/json"
	"fmt"
	"math/big"
	"strconv"
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

	// SymbolSpaces 是程序级 symbol-space layout（abstract-machine 方言）。
	//
	// `SLOT_COMPLETE` 的 `BindingAddr(space, slot)` 靠它还原成 Symbol
	// （对应 `qy/ir/layout.py::SymbolSpaceLayout` 与 `machine.py::_slot_symbol`）。
	// compat 方言为空。
	SymbolSpaces []SymbolSpaceLayout `json:"symbol_spaces,omitempty"`
}

// BindingSlot 是一个 once-complete 绑定槽（对应 `qy.ir.layout.BindingSlot`）。
type BindingSlot struct {
	Symbol string `json:"symbol"`
	Index  int    `json:"index"`
	Source string `json:"source"`
}

// SymbolSpaceLayout 是一个词法符号空间的稳定 id / parent / slots
// （对应 `qy.ir.layout.SymbolSpaceLayout`）。
type SymbolSpaceLayout struct {
	ID     int           `json:"id"`
	Name   string        `json:"name"`
	Parent *int          `json:"parent"`
	Slots  []BindingSlot `json:"slots"`
}

// BindingAddr 是 `SLOT_COMPLETE` 的绑定地址（对应 Python 的 `LIRBindingAddr`）。
type BindingAddr struct {
	Space int
	Slot  int
}

// Function 是一个字节码函数。
type Function struct {
	Name          string        `json:"name"`
	Params        []string      `json:"params"`
	RegisterCount int           `json:"register_count"`
	Instructions  []Instruction `json:"instructions"`
	// `&rest` / `&body` 变参名；空串表示定长参数。
	Rest string `json:"rest"`
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

// UnmarshalJSON 实现通用操作数解码。
//
// 关键：必须用 `json.Decoder.UseNumber()`。`qy export` 直接把 Python 任意精度
// int 写进 `{"type":"int","value":<整数>}`；默认的 `json.Unmarshal` 会在词法阶段
// 把超过 2^53 的整数四舍五入成 float64，reviver 无法恢复精度，装载即丢精度。
// 开启 UseNumber 后数字保留为 `json.Number`（原始十进制 token），由调用方按需
// 精确解析为 int / *big.Int / float64。
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
		decoder := json.NewDecoder(bytes.NewReader(raw.Value))
		decoder.UseNumber()
		var value interface{}
		if err := decoder.Decode(&value); err != nil {
			return fmt.Errorf("decode operand value: %w", err)
		}
		o.Value = value
	}
	return nil
}

// AsInt 把操作数载荷还原为整数。
func (o *Operand) AsInt() int { return AsInt(o.Value) }

// AsFloat 把操作数载荷还原为 float64（供 `type: float` 使用）。
func (o *Operand) AsFloat() float64 {
	switch v := o.Value.(type) {
	case float64:
		return v
	case json.Number:
		parsed, err := v.Float64()
		if err != nil {
			return 0
		}
		return parsed
	case int:
		return float64(v)
	case int64:
		return float64(v)
	case *big.Int:
		f, _ := new(big.Float).SetInt(v).Float64()
		return f
	case string:
		parsed, err := strconv.ParseFloat(v, 64)
		if err != nil {
			return 0
		}
		return parsed
	}
	return 0
}

// AsBigInt 把操作数载荷还原为任意精度整数（对应 Python 的精确 int）。
func (o *Operand) AsBigInt() *big.Int { return ExactBigInt(o.Value) }

// AsBindingAddr 还原 `binding_addr` 载荷（`SLOT_COMPLETE` 的地址）。
func (o *Operand) AsBindingAddr() (BindingAddr, bool) {
	entry, ok := o.Value.(map[string]interface{})
	if !ok {
		return BindingAddr{}, false
	}
	space := AsInt(entry["space"])
	slot := AsInt(entry["slot"])
	return BindingAddr{Space: space, Slot: slot}, true
}

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
	case json.Number:
		return v.String() != "0"
	case int:
		return v != 0
	case int64:
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
//
// 处理 UseNumber 打开后的 `json.Number`：优先按 int64 精确解析，只有带小数点 /
// 指数的 token 才退回 float64。`*big.Int` 只可能在已解码的语义值里出现。
func AsInt(value interface{}) int {
	switch v := value.(type) {
	case bool:
		if v {
			return 1
		}
		return 0
	case float64:
		return int(v)
	case json.Number:
		if parsed, err := v.Int64(); err == nil {
			return int(parsed)
		}
		if parsed, err := v.Float64(); err == nil {
			return int(parsed)
		}
	case int:
		return v
	case int64:
		return int(v)
	case *big.Int:
		if v.IsInt64() {
			return int(v.Int64())
		}
		return 0
	case string:
		var parsed int
		if _, err := fmt.Sscanf(v, "%d", &parsed); err == nil {
			return parsed
		}
	}
	return 0
}

// ExactBigInt 把通用 JSON 值精确还原为任意精度整数。
//
// 这是交换格式里 Python int 的唯一正确解码路径：绝不经过 float64。
func ExactBigInt(value interface{}) *big.Int {
	switch v := value.(type) {
	case *big.Int:
		return new(big.Int).Set(v)
	case json.Number:
		if parsed, ok := new(big.Int).SetString(v.String(), 10); ok {
			return parsed
		}
		// 带小数 / 指数的 token 不是整数字面量，退回截断值。
		if f, err := v.Float64(); err == nil {
			return bigFromFloat(f)
		}
	case int:
		return big.NewInt(int64(v))
	case int64:
		return big.NewInt(v)
	case float64:
		return bigFromFloat(v)
	case string:
		if parsed, ok := new(big.Int).SetString(v, 10); ok {
			return parsed
		}
	}
	return big.NewInt(0)
}

// bigFromFloat 把宿主 float64 截断为 big.Int（等价 Go 的类型转换语义）。
func bigFromFloat(value float64) *big.Int {
	if result, _ := new(big.Float).SetFloat64(value).Int(nil); result != nil {
		return result
	}
	return big.NewInt(0)
}
