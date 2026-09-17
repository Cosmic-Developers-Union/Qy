package vm

import (
	"math/big"
	"strconv"
	"strings"
	"unicode/utf8"
)

// 符号空间（symbol-space）与字面量解析。
//
// 真源：
//   - `qy/session/runtime_space.py`（RuntimeSpace：resolve / define / child）
//   - `qy/session/pre_ss.py`（lisp-ss / number-ss / char-ss / string-ss 与
//     `try_default_literal` / `parse_number_literal` / `parse_string_literal` /
//     `parse_char_literal`）
//
// 结构：每个 Env 就是一个 symbol-space，parent 是链上的下一个空间。
// Resolve 先做链 walk，全链 miss 之后才走字面量解析 —— 与 Python
// `RuntimeSpace.resolve`（链 miss → profile literal fallback）一致。
//
// 本文件是 `qy/backend/typescript/src/environment.ts` 的 Go 同构移植。

// ---------------------------------------------------------------------------
// 字面量解析（qy/session/pre_ss.py）
// ---------------------------------------------------------------------------

var charNamed = map[string]string{
	"space":     " ",
	"newline":   "\n",
	"tab":       "\t",
	"return":    "\r",
	"null":      "\x00",
	"nul":       "\x00",
	"backspace": "\x08",
	"delete":    "\x7f",
	"escape":    "\x1b",
	"alarm":     "\x07",
	"vtab":      "\x0b",
	"formfeed":  "\x0c",
}

func isStringLiteral(name string) bool {
	return strings.HasPrefix(name, "\"") || strings.HasPrefix(name, "r\"")
}

func isCharLiteral(name string) bool {
	return strings.HasPrefix(name, "#\\") && len(name) > 2
}

// parseIntLiteral 是 Python `int(name)`（十进制）的对应实现。
//
// 返回任意精度 `*big.Int`：Python 的 int 没有位宽上限，超过 2^53 的字面量
// 必须精确保留（`qy/session/pre_ss.py::parse_number_literal`）。
//
// 注意 Python 的 `int()` 默认进制不接受 `0x` / `0o` / `0b` 前缀，
// 所以 Qy 的 number-ss 也不把 `0x10` 当字面量。
func parseIntLiteral(name string) (*big.Int, bool) {
	text := strings.TrimSpace(name)
	if text == "" {
		return nil, false
	}
	if !isIntSpelling(text) {
		return nil, false
	}
	cleaned := strings.ReplaceAll(text, "_", "")
	value, ok := new(big.Int).SetString(cleaned, 10)
	if !ok {
		return nil, false
	}
	return value, true
}

// isIntSpelling 判断是否符合 `[+-]?\d(_?\d)*`。
func isIntSpelling(text string) bool {
	i := 0
	if text[0] == '+' || text[0] == '-' {
		i = 1
	}
	if i >= len(text) {
		return false
	}
	seenDigit := false
	prevUnderscore := false
	for ; i < len(text); i++ {
		c := text[i]
		if c >= '0' && c <= '9' {
			seenDigit = true
			prevUnderscore = false
			continue
		}
		if c == '_' && !prevUnderscore && i+1 < len(text) && text[i+1] >= '0' && text[i+1] <= '9' {
			prevUnderscore = true
			continue
		}
		return false
	}
	return seenDigit && !prevUnderscore
}

// parseFloatLiteral 是 Python `float(name)` 的近似实现。
//
// 与 Python 一样拒绝 inf / nan（`parse_number_literal` 显式过滤）。
func parseFloatLiteral(name string) (float64, bool) {
	text := strings.TrimSpace(name)
	if text == "" {
		return 0, false
	}
	if !isFloatSpelling(text) {
		return 0, false
	}
	if !strings.ContainsAny(text, "0123456789") {
		return 0, false
	}
	value, err := strconv.ParseFloat(strings.ReplaceAll(text, "_", ""), 64)
	if err != nil {
		return 0, false
	}
	if value != value || value > maxFloat64 || value < -maxFloat64 {
		return 0, false
	}
	return value, true
}

const maxFloat64 = 1.7976931348623157e308

// isFloatSpelling 判断是否符合 `[+-]?digits?(.digits?)?([eE][+-]?digits)?`。
func isFloatSpelling(text string) bool {
	i := 0
	if i < len(text) && (text[i] == '+' || text[i] == '-') {
		i++
	}
	i = consumeDigits(text, i)
	if i < len(text) && text[i] == '.' {
		i++
		i = consumeDigits(text, i)
	}
	if i < len(text) && (text[i] == 'e' || text[i] == 'E') {
		i++
		if i < len(text) && (text[i] == '+' || text[i] == '-') {
			i++
		}
		before := i
		i = consumeDigits(text, i)
		if i == before {
			return false
		}
	}
	return i == len(text)
}

// consumeDigits 消费 `\d(_?\d)*`，返回新的下标。
func consumeDigits(text string, i int) int {
	for i < len(text) {
		if text[i] < '0' || text[i] > '9' {
			break
		}
		i++
		if i < len(text) && text[i] == '_' && i+1 < len(text) && text[i+1] >= '0' && text[i+1] <= '9' {
			i++
		}
	}
	return i
}

// parseCharLiteral 解析字符字面量；失败返回 (nil, false)。
func parseCharLiteral(name string) (*CharValue, bool) {
	if !isCharLiteral(name) {
		return nil, false
	}
	body := name[2:]
	if utf8.RuneCountInString(body) == 1 {
		return NewChar(body), true
	}
	lower := strings.ToLower(body)
	if named, ok := charNamed[lower]; ok {
		return NewChar(named), true
	}
	if strings.HasPrefix(lower, "u") && (len(body) == 5 || len(body) == 9) {
		return charFromHex(body[1:])
	}
	if strings.HasPrefix(lower, "x") && len(body) == 3 {
		return charFromHex(body[1:])
	}
	return nil, false
}

func charFromHex(hexPart string) (*CharValue, bool) {
	code, err := strconv.ParseInt(hexPart, 16, 64)
	if err != nil || code < 0 || code > 0x10FFFF {
		return nil, false
	}
	if code >= 0xD800 && code <= 0xDFFF {
		// Python 的 chr() 对代理区抛 ValueError，pre_ss 把它当解析失败。
		return nil, false
	}
	return NewChar(string(rune(code))), true
}

// parseStringLiteral 是 Python 字符串字面量解析（`ast.literal_eval` 的对应）。
//
// 支持 `"..."` 与 `r"..."`，以及常规转义 \n \t \r \\ \" \' \xNN \uNNNN
// \UNNNNNNNN \0 \a \b \f \v。
func parseStringLiteral(name string) (*StringValue, bool) {
	raw := false
	var body string
	switch {
	case strings.HasPrefix(name, "r\""):
		raw = true
		body = name[2:]
	case strings.HasPrefix(name, "\""):
		body = name[1:]
	default:
		return nil, false
	}
	if !strings.HasSuffix(body, "\"") {
		return nil, false
	}
	body = body[:len(body)-1]

	var out strings.Builder
	for i := 0; i < len(body); i++ {
		ch := body[i]
		if ch != '\\' || raw {
			out.WriteByte(ch)
			continue
		}
		i++
		if i >= len(body) {
			return nil, false
		}
		esc := body[i]
		switch esc {
		case 'n':
			out.WriteByte('\n')
		case 't':
			out.WriteByte('\t')
		case 'r':
			out.WriteByte('\r')
		case '\\':
			out.WriteByte('\\')
		case '\'':
			out.WriteByte('\'')
		case '"':
			out.WriteByte('"')
		case 'a':
			out.WriteByte('\a')
		case 'b':
			out.WriteByte('\b')
		case 'f':
			out.WriteByte('\f')
		case 'v':
			out.WriteByte('\v')
		case '0':
			out.WriteByte(0)
		case 'x':
			decoded, ok := decodeHexEscape(body, i+1, 2)
			if !ok {
				return nil, false
			}
			out.WriteString(decoded)
			i += 2
		case 'u':
			decoded, ok := decodeHexEscape(body, i+1, 4)
			if !ok {
				return nil, false
			}
			out.WriteString(decoded)
			i += 4
		case 'U':
			decoded, ok := decodeHexEscape(body, i+1, 8)
			if !ok {
				return nil, false
			}
			out.WriteString(decoded)
			i += 8
		default:
			// Python 会保留未知转义的反斜杠
			out.WriteByte('\\')
			out.WriteByte(esc)
		}
	}
	return NewString(out.String()), true
}

func decodeHexEscape(body string, start, length int) (string, bool) {
	if start+length > len(body) {
		return "", false
	}
	hexPart := body[start : start+length]
	code, err := strconv.ParseInt(hexPart, 16, 64)
	if err != nil || code < 0 || code > 0x10FFFF {
		return "", false
	}
	return string(rune(code)), true
}

// tryDefaultLiteral 是 `try_default_literal` 的对应实现。
// 无法解析为字面量时返回 (nil, false)。
func tryDefaultLiteral(name string) (Value, bool) {
	switch name {
	case "T", "true":
		return QyT, true
	case "nil", "false":
		return QyNil, true
	case "none":
		return QyNone, true
	}
	if isCharLiteral(name) {
		if value, ok := parseCharLiteral(name); ok {
			return value, true
		}
	}
	if isStringLiteral(name) {
		if value, ok := parseStringLiteral(name); ok {
			return value, true
		}
	}
	if intValue, ok := parseIntLiteral(name); ok {
		return NewBigInt(intValue), true
	}
	if floatValue, ok := parseFloatLiteral(name); ok {
		return NewFloat(floatValue), true
	}
	return nil, false
}

// TryDefaultLiteral 是 `try_default_literal` 的公开入口（供 stdlib 归一实参用）。
func TryDefaultLiteral(name string) (Value, bool) { return tryDefaultLiteral(name) }

// ---------------------------------------------------------------------------
// symbol-space
// ---------------------------------------------------------------------------

// Env 是一个 symbol-space（作用域）。
type Env struct {
	parent   *Env
	bindings map[string]Value
	name     string
}

// NewEnv 构造一个 symbol-space；parent 为 nil 表示链尾。
func NewEnv(parent *Env) *Env {
	return &Env{parent: parent, bindings: map[string]Value{}}
}

// NewNamedEnv 构造带名字的 symbol-space（用于标准 profile 链诊断）。
func NewNamedEnv(parent *Env, name string) *Env {
	return &Env{parent: parent, bindings: map[string]Value{}, name: name}
}

// Parent 返回链上的下一个空间。
func (e *Env) Parent() *Env { return e.parent }

// Name 返回空间名。
func (e *Env) Name() string { return e.name }

// Child 新建子空间（let / lambda / module / 函数调用帧都走它）。
func (e *Env) Child() *Env { return NewEnv(e) }

// ChildWith 新建带初始绑定的子空间。
func (e *Env) ChildWith(bindings map[string]Value) *Env {
	child := NewEnv(e)
	for name, value := range bindings {
		child.bindings[name] = value
	}
	return child
}

// LocalBindings 返回当前空间内的绑定快照（对应 `local_bindings`）。
func (e *Env) LocalBindings() map[string]Value {
	result := make(map[string]Value, len(e.bindings))
	for name, value := range e.bindings {
		result[name] = value
	}
	return result
}

// HasLocal 判断当前空间是否已绑定该名字。
func (e *Env) HasLocal(name string) bool {
	_, ok := e.bindings[name]
	return ok
}

// Define 绑定当前空间内的名字（允许重绑定）。对应 `SymbolSpace.define`。
func (e *Env) Define(name string, value Value) Value {
	e.bindings[name] = value
	return value
}

// DefineOnce 绑定名字；当前空间已绑定则报错。对应 `SymbolSpace.define_once`。
func (e *Env) DefineOnce(name string, value Value) (Value, error) {
	if _, exists := e.bindings[name]; exists {
		return nil, NewResolveError(
			"symbol '" + name + "' is already bound in this scope; use 'let' to shadow")
	}
	e.bindings[name] = value
	return value, nil
}

// LookupLocal 单层查找（不递归 parent）。
func (e *Env) LookupLocal(sym *Symbol) (Value, bool) {
	value, ok := e.bindings[sym.Name]
	return value, ok
}

// ResolveRaw 沿链查找，不落到字面量解析（对应 `SymbolSpace.resolve`）。
func (e *Env) ResolveRaw(sym *Symbol) (Value, bool) {
	for current := e; current != nil; current = current.parent {
		if value, ok := current.bindings[sym.Name]; ok {
			return value, true
		}
	}
	return nil, false
}

// Resolve 完整解析：链 walk 命中即返回；全链 miss 后回退到字面量解析。
// 解析失败返回 *ResolveError（对应 `resolve_default_literal`）。
func (e *Env) Resolve(sym *Symbol) (Value, error) {
	if value, ok := e.ResolveRaw(sym); ok {
		return value, nil
	}
	if literal, ok := tryDefaultLiteral(sym.Name); ok {
		return literal, nil
	}
	return nil, NewResolveError("unresolved symbol '" + sym.Name + "'")
}

// MustResolve 与 Resolve 相同，但解析失败时 panic（仅供内部断言使用）。
func (e *Env) MustResolve(sym *Symbol) Value {
	value, err := e.Resolve(sym)
	if err != nil {
		panic(err)
	}
	return value
}

// Describe 用于错误信息的简单描述。
func Describe(value Value) string {
	switch v := value.(type) {
	case NilValue:
		return "nil"
	case TValue:
		return "T"
	case NoneValue:
		return "none"
	case *Symbol:
		return v.Name
	case *Chain:
		return "(chain)"
	case *Number:
		if v.IsInt {
			return v.Int.String()
		}
		return strconv.FormatFloat(v.Float, 'g', -1, 64)
	case *big.Int:
		return v.String()
	case *StringValue:
		return "\"" + v.Value + "\""
	case nil:
		return "none"
	}
	return FormatValue(value)
}
