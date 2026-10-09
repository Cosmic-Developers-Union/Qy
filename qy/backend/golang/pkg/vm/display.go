package vm

import (
	"bytes"
	"encoding/json"
	"fmt"
	"math"
	"math/big"
	"sort"
	"strconv"
	"strings"
)

// 值的文本表示，必须与 Python 侧 `qy/display.py::format_value` 逐字节一致。
//
// 对应关系（`qy/backend/typescript/src/display.ts` 的 Go 同构移植）：
//
//	nil → "nil"；T → "T"；none → "none"
//	NumberValue → 整数十进制；浮点用 Python repr 规则
//	StringValue → 原始文本（不加引号）
//	Chain → "(a b c)" / "(a b . c)"
//	TupleValue → "(a b)"；ListValue → "[a b]"；DictValue → "{k v}"；SetValue → "#{a b}"
//	Symbol → reader 的 write（必要时 JSON 转义）

// PyFloatRepr 是 Python `repr(float)` 的近似实现。
//
// Python 的浮点 repr 是「最短可回环」表示，且：
//   - 整数浮点必须带 `.0`（`4.0`）；
//   - 指数形式出现在 exp < -4 或 exp >= 16；
//   - 指数至少两位（`1e-07`）。
//
// Go 的 `strconv.FormatFloat(x, 'e', -1, 64)` 同样给出最短可回环数字序列，
// 因此以它的尾数与指数为基准重新排版。
func PyFloatRepr(x float64) string {
	switch {
	case math.IsNaN(x):
		return "nan"
	case math.IsInf(x, 1):
		return "inf"
	case math.IsInf(x, -1):
		return "-inf"
	case x == 0:
		if math.Signbit(x) {
			return "-0.0"
		}
		return "0.0"
	}

	text := strconv.FormatFloat(x, 'e', -1, 64)
	sign := ""
	if strings.HasPrefix(text, "-") {
		sign = "-"
		text = text[1:]
	}
	epos := strings.IndexAny(text, "eE")
	if epos < 0 {
		return sign + text
	}
	mantissa := strings.Replace(text[:epos], ".", "", 1)
	exp, err := strconv.Atoi(text[epos+1:])
	if err != nil {
		return sign + text
	}

	if exp < -4 || exp >= 16 {
		head := mantissa
		if len(mantissa) > 1 {
			head = mantissa[:1] + "." + mantissa[1:]
		}
		expSign := "+"
		if exp < 0 {
			expSign = "-"
		}
		expText := strconv.Itoa(absInt(exp))
		if len(expText) < 2 {
			expText = "0" + expText
		}
		return sign + head + "e" + expSign + expText
	}

	var intPart, fracPart string
	if exp >= 0 {
		if len(mantissa) > exp+1 {
			intPart = mantissa[:exp+1]
			fracPart = mantissa[exp+1:]
		} else {
			intPart = mantissa + strings.Repeat("0", exp+1-len(mantissa))
			fracPart = ""
		}
	} else {
		intPart = "0"
		fracPart = strings.Repeat("0", -exp-1) + mantissa
	}
	if fracPart == "" {
		fracPart = "0"
	}
	return sign + intPart + "." + fracPart
}

func absInt(v int) int {
	if v < 0 {
		return -v
	}
	return v
}

// WriteSymbol 返回 Symbol 的 write 形式（字符串字面量符号原样输出）。
func WriteSymbol(value *Symbol) string {
	if strings.HasPrefix(value.Name, "\"") || strings.HasPrefix(value.Name, "r\"") {
		return value.Name
	}
	return encodeSymbol(value.Name)
}

func encodeSymbol(name string) string {
	if name == "" {
		return quoteJSON(name)
	}
	for _, r := range name {
		if isSpaceRune(r) || strings.ContainsRune("()\"';", r) {
			return quoteJSON(name)
		}
	}
	return name
}

func isSpaceRune(r rune) bool {
	switch r {
	case ' ', '\t', '\n', '\v', '\f', '\r':
		return true
	}
	return false
}

// quoteJSON 等价于 JS `JSON.stringify(string)`（不转义非 ASCII，不转义 HTML 字符）。
func quoteJSON(text string) string {
	var buf bytes.Buffer
	encoder := json.NewEncoder(&buf)
	encoder.SetEscapeHTML(false)
	if err := encoder.Encode(text); err != nil {
		return "\"" + text + "\""
	}
	return strings.TrimRight(buf.String(), "\n")
}

func formatCons(value *Chain) string {
	parts := []string{}
	var current Value = value
	for {
		c, ok := current.(*Chain)
		if !ok {
			break
		}
		parts = append(parts, FormatValue(c.Head))
		current = c.Tail
	}
	if IsNil(current) {
		return "(" + strings.Join(parts, " ") + ")"
	}
	return "(" + strings.Join(parts, " ") + " . " + FormatValue(current) + ")"
}

// pyReprString 是 Python `repr(str)` 的近似（单引号优先）。
func pyReprString(value string) string {
	escaped := strings.NewReplacer("\\", "\\\\", "\n", "\\n", "\t", "\\t", "'", "\\'").Replace(value)
	if !strings.Contains(value, "'") || strings.Contains(value, "\"") {
		return "'" + escaped + "'"
	}
	return "\"" + strings.NewReplacer("\\", "\\\\", "\"", "\\\"").Replace(value) + "\""
}

// FormatValue 是与 `qy/display.py::format_value` 对应的格式化入口。
func FormatValue(value Value) string {
	switch v := value.(type) {
	case nil:
		return "none"
	case NilValue:
		return "nil"
	case TValue:
		return "T"
	case NoneValue:
		return "none"
	case *Number:
		// 整型家族走 big.Int.String()：纯十进制，不会出现科学计数法或宿主后缀。
		return v.String()
	case *StringValue:
		return v.Value
	case *Chain:
		return formatCons(v)
	case *TupleValue:
		return "(" + formatList(v.Items) + ")"
	case *ListValue:
		return "[" + formatList(v.Items) + "]"
	case *DictValue:
		parts := make([]string, 0, len(v.Entries))
		for _, entry := range v.Entries {
			parts = append(parts, FormatValue(entry.Key)+" "+FormatValue(entry.Value))
		}
		return "{" + strings.Join(parts, " ") + "}"
	case *SetValue:
		items := make([]string, 0, len(v.Items))
		for _, item := range v.Items {
			items = append(items, FormatValue(item))
		}
		sort.Strings(items)
		return "#{" + strings.Join(items, " ") + "}"
	case *Symbol:
		return WriteSymbol(v)
	case *CharValue:
		// display 语义：字符与字符串一样输出原文本（write 才用 `#\a`）。
		return v.Value
	case bool:
		if v {
			return "true"
		}
		return "false"
	case int:
		return strconv.Itoa(v)
	case int64:
		return strconv.FormatInt(v, 10)
	case *big.Int:
		// 宿主任意精度整型（nested 载荷）也输出纯十进制。
		return v.String()
	case float64:
		if v == math.Trunc(v) && !math.IsInf(v, 0) {
			return formatInteger(v)
		}
		return PyFloatRepr(v)
	case []Value:
		return "[" + formatList(v) + "]"
	case *FunctionValue:
		return "<function " + v.Fn.Name + ">"
	case *PureOperator:
		return "<operator " + v.Name + ">"
	case *RawOperator:
		return "<operator " + v.Name + ">"
	case *EffectDefinition:
		return "<effect " + v.Name + ">"
	case *Continuation:
		return "<continuation>"
	case *ModuleValue:
		return "<module " + v.Name + ">"
	case *Env:
		return "<symbol-space>"
	case SlotTokenType:
		return "<slot>"
	case *HandlerSpec:
		return "<handler " + v.Effect + ">"
	}
	return describeFallback(value)
}

func describeFallback(value Value) string {
	return fmt.Sprintf("%v", value)
}

// formatInteger 把宿主 float64（整数值）格式化为十进制文本。
// Qy 语义整型不走这里（见 `Number.String`，用 big.Int）。
func formatInteger(v float64) string {
	return strconv.FormatFloat(v, 'f', -1, 64)
}

func formatList(items []Value) string {
	parts := make([]string, 0, len(items))
	for _, item := range items {
		parts = append(parts, FormatValue(item))
	}
	return strings.Join(parts, " ")
}

// IsDefinitionArtifact 对应 `qy/cli/_common.py::_is_definition_artifact`：
// 这些值由绑定形式求值产生，不是用户可见表达式值，`qy run` 不打印。
func IsDefinitionArtifact(value Value) bool {
	if value == nil {
		return true
	}
	switch value.(type) {
	case *FunctionValue, *ModuleValue, *EffectDefinition:
		return true
	}
	return false
}
