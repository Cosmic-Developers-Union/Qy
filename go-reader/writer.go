package reader

import (
	"encoding/json"
	"math"
	"strings"
)

// Write serializes a form back to Qy source text.
func Write(form Form) string {
	switch f := form.(type) {
	case Symbol:
		if isStringSymbol(f.Name) {
			return f.Name
		}
		return encodeSymbol(f.Name)
	case *Chain:
		return writeChain(f)
	case Nil:
		return "()"
	default:
		return "()"
	}
}

func writeChain(chain *Chain) string {
	var items []string
	var current Form = chain
	for IsChain(current) {
		items = append(items, Write(Car(current)))
		current = Cdr(current)
	}
	if !IsNil(current) {
		return "(" + strings.Join(items, " ") + " . " + Write(current) + ")"
	}
	// Surface quote shorthand
	if len(items) == 2 && items[0] == "quote" {
		return "'" + items[1]
	}
	if len(items) == 2 && items[0] == "quasiquote" {
		return "`" + items[1]
	}
	return "(" + strings.Join(items, " ") + ")"
}

// WriteProgram serializes a list of forms separated by newlines.
func WriteProgram(forms []Form) string {
	parts := make([]string, len(forms))
	for i, f := range forms {
		parts[i] = Write(f)
	}
	return strings.Join(parts, "\n")
}

func isStringSymbol(name string) bool {
	return strings.HasPrefix(name, `"`) || strings.HasPrefix(name, `r"`) || strings.HasPrefix(name, `R"`)
}

func encodeSymbol(name string) string {
	if canWriteBare(name) {
		return name
	}
	b, _ := json.Marshal(name)
	return string(b)
}

func canWriteBare(name string) bool {
	if name == "" {
		return false
	}
	for _, r := range name {
		switch r {
		case '(', ')', '"', '\'', ';':
			return false
		}
		if r <= ' ' {
			return false
		}
	}
	return true
}

// EncodeLiteral encodes a Go value as a Qy source literal string.
func EncodeLiteral(v any) string {
	switch val := v.(type) {
	case string:
		b, _ := json.Marshal(val)
		return string(b)
	case bool:
		if val {
			return "true"
		}
		return "false"
	case int:
		return strings.TrimRight(strings.TrimRight(json.Number(intToString(val)).String(), "0"), ".")
	case int64:
		return strings.TrimRight(strings.TrimRight(json.Number(int64ToString(val)).String(), "0"), ".")
	case float64:
		if math.IsInf(val, 0) || math.IsNaN(val) {
			panic("cannot write non-finite float literal as qy source")
		}
		return strings.TrimRight(strings.TrimRight(floatToString(val), "0"), ".")
	case nil:
		return "none"
	default:
		panic("cannot write literal")
	}
}

func intToString(i int) string {
	return json.Number(strings.TrimRight(strings.TrimRight(
		func() string { b, _ := json.Marshal(i); return string(b) }(), "0"), ".")).String()
}

func int64ToString(i int64) string {
	b, _ := json.Marshal(i)
	return string(b)
}

func floatToString(f float64) string {
	b, _ := json.Marshal(f)
	return string(b)
}
