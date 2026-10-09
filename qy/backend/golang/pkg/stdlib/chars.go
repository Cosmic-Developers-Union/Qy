package stdlib

import (
	"unicode"
	"unicode/utf8"

	"github.com/Cosmic-Developers-Union/Qy/qy/backend/golang/pkg/vm"
)

// qy.char 模块算子（对应 `qy/std/chars.py`）。

func requireChar(value vm.Value, op string) (*vm.CharValue, error) {
	if c, ok := value.(*vm.CharValue); ok {
		return c, nil
	}
	return nil, vm.NewTypeError(op + ": expected char")
}

func charRune(c *vm.CharValue) rune {
	return []rune(c.Value)[0]
}

func charCompare(op string, cmp func(a, b rune) bool) func(args []vm.Value) (vm.Value, error) {
	return func(args []vm.Value) (vm.Value, error) {
		a, err := requireChar(args[0], op)
		if err != nil {
			return nil, err
		}
		b, err := requireChar(args[1], op)
		if err != nil {
			return nil, err
		}
		if cmp(charRune(a), charRune(b)) {
			return vm.QyT, nil
		}
		return vm.QyNil, nil
	}
}

func charPredicate(op string, pred func(r rune) bool) func(args []vm.Value) (vm.Value, error) {
	return func(args []vm.Value) (vm.Value, error) {
		c, err := requireChar(args[0], op)
		if err != nil {
			return nil, err
		}
		if pred(charRune(c)) {
			return vm.QyT, nil
		}
		return vm.QyNil, nil
	}
}

func charBindings() map[string]func(args []vm.Value) (vm.Value, error) {
	return map[string]func(args []vm.Value) (vm.Value, error){
		"char?": func(args []vm.Value) (vm.Value, error) {
			if _, ok := args[0].(*vm.CharValue); ok {
				return vm.QyT, nil
			}
			return vm.QyNil, nil
		},
		"char=?":  charCompare("char=?", func(a, b rune) bool { return a == b }),
		"char<?":  charCompare("char<?", func(a, b rune) bool { return a < b }),
		"char<=?": charCompare("char<=?", func(a, b rune) bool { return a <= b }),
		"char>?":  charCompare("char>?", func(a, b rune) bool { return a > b }),
		"char>=?": charCompare("char>=?", func(a, b rune) bool { return a >= b }),
		"char->integer": func(args []vm.Value) (vm.Value, error) {
			c, err := requireChar(args[0], "char->integer")
			if err != nil {
				return nil, err
			}
			return vm.NewInt(int64(charRune(c))), nil
		},
		"integer->char": func(args []vm.Value) (vm.Value, error) {
			n, ok := args[0].(*vm.Number)
			if !ok || !n.IsInt {
				return nil, vm.NewTypeError("integer->char: expected integer")
			}
			if !n.BigPayload().IsInt64() {
				return nil, vm.NewTypeError("integer->char: invalid codepoint")
			}
			code := n.BigPayload().Int64()
			if code < 0 || code > 0x10FFFF || (code >= 0xD800 && code <= 0xDFFF) {
				return nil, vm.NewTypeError("integer->char: invalid codepoint")
			}
			return vm.NewChar(string(rune(code))), nil
		},
		"char-alphabetic?": charPredicate("char-alphabetic?", unicode.IsLetter),
		"char-numeric?":    charPredicate("char-numeric?", unicode.IsDigit),
		"char-whitespace?": charPredicate("char-whitespace?", unicode.IsSpace),
		"char-upper-case?": charPredicate("char-upper-case?", unicode.IsUpper),
		"char-lower-case?": charPredicate("char-lower-case?", unicode.IsLower),
		"char-upcase": func(args []vm.Value) (vm.Value, error) {
			c, err := requireChar(args[0], "char-upcase")
			if err != nil {
				return nil, err
			}
			mapped := fullUpper(c.Value)
			if utf8.RuneCountInString(mapped) != 1 {
				return nil, vm.NewRuntimeError("char value must contain exactly one Unicode scalar")
			}
			return vm.NewChar(mapped), nil
		},
		"char-downcase": func(args []vm.Value) (vm.Value, error) {
			c, err := requireChar(args[0], "char-downcase")
			if err != nil {
				return nil, err
			}
			mapped := fullLower(c.Value)
			if utf8.RuneCountInString(mapped) != 1 {
				return nil, vm.NewRuntimeError("char value must contain exactly one Unicode scalar")
			}
			return vm.NewChar(mapped), nil
		},
		"char->string": func(args []vm.Value) (vm.Value, error) {
			c, err := requireChar(args[0], "char->string")
			if err != nil {
				return nil, err
			}
			return vm.NewString(c.Value), nil
		},
	}
}
