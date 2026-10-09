package stdlib

import (
	"fmt"
	"strings"

	"github.com/Cosmic-Developers-Union/Qy/qy/backend/golang/pkg/vm"
)

// `qy.str` 模块算子。
//
// 真源：`qy/std/strings.py`（对应 `qy/backend/typescript/src/stdlib/strings.ts`）。
// 字符串输入同时接受 StringValue 与宿主 str（Python 侧 `_extract_str` 的迁移期
// 互操作），但输出一律是 StringValue。

func optionalString(value vm.Value) (vm.Value, bool) {
	// `argAt` 对缺参返回宿主 nil（不是 QyNil），两者都必须视为「未提供」。
	if value == nil || vm.IsNil(value) {
		return nil, false
	}
	return value, true
}

func extractStr(value vm.Value, op string) (string, error) {
	switch v := value.(type) {
	case *vm.StringValue:
		return v.Value, nil
	case string:
		return v, nil
	case *vm.Symbol:
		return v.Name, nil
	}
	return "", vm.NewTypeError(op + ": expected string")
}

func extractInt(value vm.Value, op string) (int, error) {
	switch v := value.(type) {
	case *vm.Number:
		if v.IsInt && v.BigPayload().IsInt64() {
			return int(v.BigPayload().Int64()), nil
		}
	case int:
		return v, nil
	}
	return 0, vm.NewTypeError(op + ": expected integer")
}

func runeSlice(text string) []string {
	runes := []rune(text)
	parts := make([]string, 0, len(runes))
	for _, r := range runes {
		parts = append(parts, string(r))
	}
	return parts
}

// StringLength 是 `string-length`。
func StringLength(value vm.Value) (vm.Value, error) {
	text, err := extractStr(value, "string-length")
	if err != nil {
		return nil, err
	}
	return vm.NewInt(int64(len([]rune(text)))), nil
}

// StringConcat 是 `string-concat`。
func StringConcat(values ...vm.Value) (vm.Value, error) {
	var builder strings.Builder
	for _, value := range values {
		text, err := extractStr(value, "string-concat")
		if err != nil {
			return nil, err
		}
		builder.WriteString(text)
	}
	return vm.NewString(builder.String()), nil
}

// StringEq 是 `string=`。
func StringEq(a, b vm.Value) (vm.Value, error) {
	left, err := extractStr(a, "string=")
	if err != nil {
		return nil, err
	}
	right, err := extractStr(b, "string=")
	if err != nil {
		return nil, err
	}
	return boolValue(left == right), nil
}

// StringSlice 是 `string-slice`。
func StringSlice(value, start vm.Value, end vm.Value) (vm.Value, error) {
	text, err := extractStr(value, "string-slice")
	if err != nil {
		return nil, err
	}
	runes := []rune(text)
	from, err := extractInt(start, "string-slice")
	if err != nil {
		return nil, err
	}
	if _, present := optionalString(end); !present {
		return vm.NewString(string(runes[clampIndex(from, len(runes)):])), nil
	}
	to, err := extractInt(end, "string-slice")
	if err != nil {
		return nil, err
	}
	from = clampIndex(from, len(runes))
	to = clampIndex(to, len(runes))
	if to < from {
		to = from
	}
	return vm.NewString(string(runes[from:to])), nil
}

func clampIndex(index, length int) int {
	if index < 0 {
		index += length
	}
	if index < 0 {
		return 0
	}
	if index > length {
		return length
	}
	return index
}

// StringAt 是 `string-at`。
func StringAt(value, index vm.Value) (vm.Value, error) {
	text, err := extractStr(value, "string-at")
	if err != nil {
		return nil, err
	}
	runes := []rune(text)
	at, err := extractInt(index, "string-at")
	if err != nil {
		return nil, err
	}
	if at < 0 || at >= len(runes) {
		return nil, &vm.EvaluationError{Message: fmt.Sprintf("string-at: index %d out of range for string of length %d", at, len(runes))}
	}
	return vm.NewChar(string(runes[at])), nil
}

// StringFind 是 `string-find`。
func StringFind(value, needle vm.Value) (vm.Value, error) {
	text, err := extractStr(value, "string-find")
	if err != nil {
		return nil, err
	}
	sub, err := extractStr(needle, "string-find")
	if err != nil {
		return nil, err
	}
	index := strings.Index(text, sub)
	if index < 0 {
		return vm.QyNil, nil
	}
	return vm.NewInt(int64(len([]rune(text[:index])))), nil
}

// StringSplit 是 `string-split`。
func StringSplit(value, separator vm.Value) (vm.Value, error) {
	text, err := extractStr(value, "string-split")
	if err != nil {
		return nil, err
	}
	var parts []string
	if _, present := optionalString(separator); !present {
		for _, part := range strings.Fields(text) {
			if part != "" {
				parts = append(parts, part)
			}
		}
	} else {
		sep, err := extractStr(separator, "string-split")
		if err != nil {
			return nil, err
		}
		if sep == "" {
			// Python `str.split("")` 抛 `empty separator`：三宿主一致报错。
			return nil, vm.NewRuntimeError("empty separator")
		}
		parts = strings.Split(text, sep)
	}
	items := make([]vm.Value, 0, len(parts))
	for _, part := range parts {
		items = append(items, vm.NewString(part))
	}
	return vm.NewTuple(items), nil
}

// StringJoin 是 `string-join`。
func StringJoin(separator vm.Value, values ...vm.Value) (vm.Value, error) {
	sep, err := extractStr(separator, "string-join")
	if err != nil {
		return nil, err
	}
	parts := []string{}
	for _, value := range values {
		switch v := value.(type) {
		case *vm.TupleValue:
			for _, item := range v.Items {
				text, err := extractStr(item, "string-join")
				if err != nil {
					return nil, err
				}
				parts = append(parts, text)
			}
		case *vm.ListValue:
			for _, item := range v.Items {
				text, err := extractStr(item, "string-join")
				if err != nil {
					return nil, err
				}
				parts = append(parts, text)
			}
		case []vm.Value:
			for _, item := range v {
				text, err := extractStr(item, "string-join")
				if err != nil {
					return nil, err
				}
				parts = append(parts, text)
			}
		default:
			text, err := extractStr(value, "string-join")
			if err != nil {
				return nil, err
			}
			parts = append(parts, text)
		}
	}
	return vm.NewString(strings.Join(parts, sep)), nil
}

// StringReplace 是 `string-replace`。
func StringReplace(value, old, replacement vm.Value) (vm.Value, error) {
	text, err := extractStr(value, "string-replace")
	if err != nil {
		return nil, err
	}
	from, err := extractStr(old, "string-replace")
	if err != nil {
		return nil, err
	}
	to, err := extractStr(replacement, "string-replace")
	if err != nil {
		return nil, err
	}
	return vm.NewString(strings.ReplaceAll(text, from, to)), nil
}

// StringEmpty 是 `string-empty?`。
func StringEmpty(value vm.Value) (vm.Value, error) {
	text, err := extractStr(value, "string-empty?")
	if err != nil {
		return nil, err
	}
	return boolValue(text == ""), nil
}

// StringStartsWith 是 `string-starts-with?`。
func StringStartsWith(value, prefix vm.Value) (vm.Value, error) {
	text, err := extractStr(value, "string-starts-with?")
	if err != nil {
		return nil, err
	}
	head, err := extractStr(prefix, "string-starts-with?")
	if err != nil {
		return nil, err
	}
	return boolValue(strings.HasPrefix(text, head)), nil
}

// StringEndsWith 是 `string-ends-with?`。
func StringEndsWith(value, suffix vm.Value) (vm.Value, error) {
	text, err := extractStr(value, "string-ends-with?")
	if err != nil {
		return nil, err
	}
	tail, err := extractStr(suffix, "string-ends-with?")
	if err != nil {
		return nil, err
	}
	return boolValue(strings.HasSuffix(text, tail)), nil
}

// StringContains 是 `string-contains?`。
func StringContains(value, needle vm.Value) (vm.Value, error) {
	text, err := extractStr(value, "string-contains?")
	if err != nil {
		return nil, err
	}
	sub, err := extractStr(needle, "string-contains?")
	if err != nil {
		return nil, err
	}
	return boolValue(strings.Contains(text, sub)), nil
}

// StringUpper 是 `string-upper`。
func StringUpper(value vm.Value) (vm.Value, error) {
	text, err := extractStr(value, "string-upper")
	if err != nil {
		return nil, err
	}
	return vm.NewString(fullUpper(text)), nil
}

// StringLower 是 `string-lower`。
func StringLower(value vm.Value) (vm.Value, error) {
	text, err := extractStr(value, "string-lower")
	if err != nil {
		return nil, err
	}
	return vm.NewString(fullLower(text)), nil
}

// StringTrim 是 `string-trim`。
func StringTrim(value vm.Value) (vm.Value, error) {
	text, err := extractStr(value, "string-trim")
	if err != nil {
		return nil, err
	}
	return vm.NewString(strings.TrimSpace(text)), nil
}

// StringToList 是 `string->list`。
func StringToList(value vm.Value) (vm.Value, error) {
	text, err := extractStr(value, "string->list")
	if err != nil {
		return nil, err
	}
	items := []vm.Value{}
	for _, char := range runeSlice(text) {
		items = append(items, vm.NewChar(char))
	}
	return vm.NewTuple(items), nil
}

// StringToSymbol 是 `string->symbol`。
func StringToSymbol(value vm.Value) (vm.Value, error) {
	text, err := extractStr(value, "string->symbol")
	if err != nil {
		return nil, err
	}
	return vm.NewSymbol(text), nil
}

// SymbolToString 是 `symbol->string`。
func SymbolToString(value vm.Value) (vm.Value, error) {
	symbol, ok := value.(*vm.Symbol)
	if !ok {
		return nil, vm.NewTypeError("symbol->string: expected symbol")
	}
	return vm.NewString(symbol.Name), nil
}

// StringBindings 返回 `qy.str` 的算子绑定。
func StringBindings() map[string]func(args []vm.Value) (vm.Value, error) {
	return map[string]func(args []vm.Value) (vm.Value, error){
		"string?": func(args []vm.Value) (vm.Value, error) {
			switch argAt(args, 0).(type) {
			case *vm.StringValue, string:
				return vm.QyT, nil
			}
			return vm.QyNil, nil
		},
		"string-length": func(args []vm.Value) (vm.Value, error) { return StringLength(argAt(args, 0)) },
		"string-concat": func(args []vm.Value) (vm.Value, error) { return StringConcat(args...) },
		"string=":       func(args []vm.Value) (vm.Value, error) { return StringEq(argAt(args, 0), argAt(args, 1)) },
		"string-slice": func(args []vm.Value) (vm.Value, error) {
			return StringSlice(argAt(args, 0), argAt(args, 1), argAt(args, 2))
		},
		"string-at":    func(args []vm.Value) (vm.Value, error) { return StringAt(argAt(args, 0), argAt(args, 1)) },
		"string-find":  func(args []vm.Value) (vm.Value, error) { return StringFind(argAt(args, 0), argAt(args, 1)) },
		"string-split": func(args []vm.Value) (vm.Value, error) { return StringSplit(argAt(args, 0), argAt(args, 1)) },
		"string-join": func(args []vm.Value) (vm.Value, error) {
			return StringJoin(argAt(args, 0), args[minInt(1, len(args)):]...)
		},
		"string-replace": func(args []vm.Value) (vm.Value, error) {
			return StringReplace(argAt(args, 0), argAt(args, 1), argAt(args, 2))
		},
		"string-empty?": func(args []vm.Value) (vm.Value, error) { return StringEmpty(argAt(args, 0)) },
		"string-starts-with?": func(args []vm.Value) (vm.Value, error) {
			return StringStartsWith(argAt(args, 0), argAt(args, 1))
		},
		"string-ends-with?": func(args []vm.Value) (vm.Value, error) {
			return StringEndsWith(argAt(args, 0), argAt(args, 1))
		},
		"string-contains?": func(args []vm.Value) (vm.Value, error) {
			return StringContains(argAt(args, 0), argAt(args, 1))
		},
		"string-upper":   func(args []vm.Value) (vm.Value, error) { return StringUpper(argAt(args, 0)) },
		"string-lower":   func(args []vm.Value) (vm.Value, error) { return StringLower(argAt(args, 0)) },
		"string-trim":    func(args []vm.Value) (vm.Value, error) { return StringTrim(argAt(args, 0)) },
		"string->list":   func(args []vm.Value) (vm.Value, error) { return StringToList(argAt(args, 0)) },
		"string->symbol": func(args []vm.Value) (vm.Value, error) { return StringToSymbol(argAt(args, 0)) },
		"symbol->string": func(args []vm.Value) (vm.Value, error) { return SymbolToString(argAt(args, 0)) },
	}
}
