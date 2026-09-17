package vm

import "testing"

func TestTryDefaultLiteralNumbers(t *testing.T) {
	cases := []struct {
		name    string
		want    string
		isInt   bool
		missing bool
	}{
		{"42", "42", true, false},
		{"-3", "-3", true, false},
		{"+7", "7", true, false},
		{"4.5", "4.5", false, false},
		{"1_000", "1000", true, false},
		{"1e3", "1000.0", false, false},
		// 超过 2^53 的整数字面量必须精确保留（Python int 任意精度）。
		{"9007199254740993", "9007199254740993", true, false},
		{"81129638414606699710187514626049", "81129638414606699710187514626049", true, false},
		{"abc", "", false, true},
		{"0x10", "", false, true}, // Python int() 不接受 0x 前缀
	}
	for _, tc := range cases {
		value, ok := tryDefaultLiteral(tc.name)
		if tc.missing {
			if ok {
				t.Errorf("tryDefaultLiteral(%q) = %v, want miss", tc.name, value)
			}
			continue
		}
		if !ok {
			t.Errorf("tryDefaultLiteral(%q) missed", tc.name)
			continue
		}
		number, isNumber := value.(*Number)
		if !isNumber {
			t.Errorf("tryDefaultLiteral(%q) = %T, want *Number", tc.name, value)
			continue
		}
		if number.String() != tc.want {
			t.Errorf("tryDefaultLiteral(%q) = %q, want %q", tc.name, number.String(), tc.want)
		}
		if number.IsInt != tc.isInt {
			t.Errorf("tryDefaultLiteral(%q).IsInt = %v, want %v", tc.name, number.IsInt, tc.isInt)
		}
	}
}

func TestTryDefaultLiteralSingletons(t *testing.T) {
	if value, ok := tryDefaultLiteral("nil"); !ok || !IsNil(value) {
		t.Errorf("nil literal = %v (%v)", value, ok)
	}
	if value, ok := tryDefaultLiteral("T"); !ok || !IsT(value) {
		t.Errorf("T literal = %v (%v)", value, ok)
	}
	if value, ok := tryDefaultLiteral("none"); !ok || !IsNone(value) {
		t.Errorf("none literal = %v (%v)", value, ok)
	}
}

func TestTryDefaultLiteralStrings(t *testing.T) {
	value, ok := tryDefaultLiteral(`"hello"`)
	if !ok {
		t.Fatal(`string literal "hello" missed`)
	}
	text, isString := value.(*StringValue)
	if !isString || text.Value != "hello" {
		t.Fatalf("string literal = %#v", value)
	}

	escaped, ok := tryDefaultLiteral(`"a\nb"`)
	if !ok {
		t.Fatal("escaped string literal missed")
	}
	if escaped.(*StringValue).Value != "a\nb" {
		t.Fatalf("escaped string literal = %q", escaped.(*StringValue).Value)
	}

	raw, ok := tryDefaultLiteral(`r"a\nb"`)
	if !ok {
		t.Fatal("raw string literal missed")
	}
	if raw.(*StringValue).Value != `a\nb` {
		t.Fatalf("raw string literal = %q", raw.(*StringValue).Value)
	}
}

func TestTryDefaultLiteralChars(t *testing.T) {
	cases := map[string]string{
		`#\a`:       "a",
		`#\space`:   " ",
		`#\newline`: "\n",
		`#\x41`:     "A",
	}
	for name, want := range cases {
		value, ok := tryDefaultLiteral(name)
		if !ok {
			t.Errorf("char literal %q missed", name)
			continue
		}
		char, isChar := value.(*CharValue)
		if !isChar || char.Value != want {
			t.Errorf("char literal %q = %#v, want %q", name, value, want)
		}
	}
}

func TestEnvResolveFallsBackToLiteral(t *testing.T) {
	env := NewEnv(nil)
	value, err := env.Resolve(NewSymbol("42"))
	if err != nil {
		t.Fatalf("Resolve(42): %v", err)
	}
	if number, ok := value.(*Number); !ok || number.BigPayload().Int64() != 42 {
		t.Fatalf("Resolve(42) = %#v", value)
	}
	if _, err := env.Resolve(NewSymbol("nope")); err == nil {
		t.Fatal("expected unresolved symbol error")
	}
}

func TestEnvScopeShadowing(t *testing.T) {
	root := NewEnv(nil)
	root.Define("x", NewInt(1))
	child := root.Child()
	if value, _ := child.Resolve(NewSymbol("x")); value.(*Number).BigPayload().Int64() != 1 {
		t.Fatal("child should see parent binding")
	}
	child.Define("x", NewInt(2))
	if value, _ := child.Resolve(NewSymbol("x")); value.(*Number).BigPayload().Int64() != 2 {
		t.Fatal("child binding should shadow parent")
	}
	if value, _ := root.Resolve(NewSymbol("x")); value.(*Number).BigPayload().Int64() != 1 {
		t.Fatal("parent binding must not change")
	}
}

func TestEnvDefineOnceRejectsRebinding(t *testing.T) {
	env := NewEnv(nil)
	if _, err := env.DefineOnce("x", NewInt(1)); err != nil {
		t.Fatalf("first DefineOnce: %v", err)
	}
	if _, err := env.DefineOnce("x", NewInt(2)); err == nil {
		t.Fatal("second DefineOnce should fail")
	}
}

func TestChainConversion(t *testing.T) {
	chain := SliceToChain([]Value{NewInt(1), NewInt(2), NewInt(3)})
	items, err := ChainToSlice(chain)
	if err != nil {
		t.Fatalf("ChainToSlice: %v", err)
	}
	if len(items) != 3 {
		t.Fatalf("ChainToSlice = %v", items)
	}
	if _, err := ChainToSlice(NewChain(NewInt(1), NewInt(2))); err == nil {
		t.Fatal("improper chain should fail conversion")
	}
}
