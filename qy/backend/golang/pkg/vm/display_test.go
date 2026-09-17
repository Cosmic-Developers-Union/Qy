package vm

import "testing"

// 浮点显示必须与 Python `repr(float)` 对齐（`qy/display.py::format_value`）。
func TestPyFloatRepr(t *testing.T) {
	cases := map[float64]string{
		4.0:   "4.0",
		0.5:   "0.5",
		1.5:   "1.5",
		0.1:   "0.1",
		-2.25: "-2.25",
		1e16:  "1e+16",
		1e15:  "1000000000000000.0",
		1e-5:  "1e-05",
		1e-4:  "0.0001",
		0.0:   "0.0",
	}
	for value, want := range cases {
		if got := PyFloatRepr(value); got != want {
			t.Errorf("PyFloatRepr(%v) = %q, want %q", value, got, want)
		}
	}
}

func TestFormatValueSingletons(t *testing.T) {
	if got := FormatValue(QyNil); got != "nil" {
		t.Errorf("FormatValue(nil) = %q", got)
	}
	if got := FormatValue(QyT); got != "T" {
		t.Errorf("FormatValue(T) = %q", got)
	}
	if got := FormatValue(QyNone); got != "none" {
		t.Errorf("FormatValue(none) = %q", got)
	}
	if got := FormatValue(nil); got != "none" {
		t.Errorf("FormatValue(host nil) = %q", got)
	}
}

func TestFormatValueNumbers(t *testing.T) {
	if got := FormatValue(NewInt(42)); got != "42" {
		t.Errorf("FormatValue(42) = %q", got)
	}
	if got := FormatValue(NewFloat(4.0)); got != "4.0" {
		t.Errorf("FormatValue(4.0) = %q", got)
	}
	if got := FormatValue(NewFloat(1e16)); got != "1e+16" {
		t.Errorf("FormatValue(1e16) = %q", got)
	}
}

func TestFormatValueChainAndString(t *testing.T) {
	if got := FormatValue(NewString("hello")); got != "hello" {
		t.Errorf("FormatValue(string) = %q", got)
	}
	chain := SliceToChain([]Value{NewInt(1), NewInt(2), NewInt(3)})
	if got := FormatValue(chain); got != "(1 2 3)" {
		t.Errorf("FormatValue(chain) = %q", got)
	}
	improper := NewChain(NewInt(1), NewInt(2))
	if got := FormatValue(improper); got != "(1 . 2)" {
		t.Errorf("FormatValue(improper chain) = %q", got)
	}
	if got := FormatValue(NewTuple([]Value{NewInt(1), NewInt(2)})); got != "(1 2)" {
		t.Errorf("FormatValue(tuple) = %q", got)
	}
}

func TestWriteSymbolQuoting(t *testing.T) {
	if got := WriteSymbol(NewSymbol("abc")); got != "abc" {
		t.Errorf("WriteSymbol(abc) = %q", got)
	}
	if got := WriteSymbol(NewSymbol("a b")); got != `"a b"` {
		t.Errorf("WriteSymbol(a b) = %q", got)
	}
	if got := WriteSymbol(NewSymbol(`"hello"`)); got != `"hello"` {
		t.Errorf("WriteSymbol(string literal spelling) = %q", got)
	}
}

func TestIsDefinitionArtifact(t *testing.T) {
	if !IsDefinitionArtifact(nil) {
		t.Error("host nil should be a definition artifact")
	}
	if !IsDefinitionArtifact(&EffectDefinition{Name: "e"}) {
		t.Error("effect definition should be a definition artifact")
	}
	if IsDefinitionArtifact(NewInt(1)) {
		t.Error("number must not be a definition artifact")
	}
}
