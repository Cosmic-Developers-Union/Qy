package bytecode

import (
	"testing"
)

const hygieneProgram = `{
  "version": 1,
  "main": 0,
  "functions": [
    {
      "name": "<main>",
      "params": [],
      "register_count": 2,
      "instructions": [
        {"opcode": "LOAD_ENV", "operands": [
          {"type": "reg", "value": 0},
          {"type": "symbol", "value": "__qy_hygiene_def___1"}
        ]},
        {"opcode": "APPEND_RESULT", "operands": [{"type": "reg", "value": 0}]},
        {"opcode": "RETURN", "operands": [{"type": "reg", "value": 0}]}
      ]
    }
  ],
  "hygiene_bindings": {"__qy_hygiene_def___1": "+"},
  "module_macro_exports": {"M": ["my-add", "my-sub"]}
}`

func TestLoadReadsHygieneBindings(t *testing.T) {
	prog, err := Load([]byte(hygieneProgram))
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	if got := prog.HygieneBindings["__qy_hygiene_def___1"]; got != "+" {
		t.Fatalf("hygiene binding = %q, want %q", got, "+")
	}
}

func TestLoadReadsModuleMacroExports(t *testing.T) {
	prog, err := Load([]byte(hygieneProgram))
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	names := prog.ModuleMacroExports["M"]
	if len(names) != 2 || names[0] != "my-add" || names[1] != "my-sub" {
		t.Fatalf("module_macro_exports = %v, want [my-add my-sub]", names)
	}
}

func TestLoadRejectsUnknownVersion(t *testing.T) {
	if _, err := Load([]byte(`{"version": 2, "main": 0, "functions": []}`)); err == nil {
		t.Fatal("expected error for unsupported version")
	}
}

func TestOperandDecoding(t *testing.T) {
	operand := Operand{}
	if err := operand.UnmarshalJSON([]byte(`{"type": "int", "value": 7}`)); err != nil {
		t.Fatalf("UnmarshalJSON: %v", err)
	}
	if operand.Type != "int" || operand.AsInt() != 7 {
		t.Fatalf("operand = %+v", operand)
	}

	regTuple := Operand{}
	if err := regTuple.UnmarshalJSON([]byte(`{"type": "reg_tuple", "value": [1, 2, 3]}`)); err != nil {
		t.Fatalf("UnmarshalJSON: %v", err)
	}
	items := regTuple.AsIntList()
	if len(items) != 3 || items[0] != 1 || items[2] != 3 {
		t.Fatalf("reg_tuple = %v", items)
	}

	specs := Operand{}
	if err := specs.UnmarshalJSON([]byte(
		`{"type": "import_specs", "value": [{"name": "a", "alias": "b"}]}`)); err != nil {
		t.Fatalf("UnmarshalJSON: %v", err)
	}
	parsed := specs.AsImportSpecs()
	if len(parsed) != 1 || parsed[0].Name != "a" || parsed[0].Alias != "b" {
		t.Fatalf("import_specs = %+v", parsed)
	}
}

// JSON 里的整数必须精确保留：默认 json.Unmarshal 会在 2^53 之后丢精度。
func TestOperandKeepsBigIntegerPrecision(t *testing.T) {
	operand := Operand{}
	if err := operand.UnmarshalJSON([]byte(`{"type": "int", "value": 9007199254740993}`)); err != nil {
		t.Fatalf("UnmarshalJSON: %v", err)
	}
	if got := operand.AsBigInt().String(); got != "9007199254740993" {
		t.Fatalf("AsBigInt = %s, want 9007199254740993", got)
	}
	// 同一 token 若经 float64 中转会变成 9007199254740992。
	if got := operand.AsInt(); got != 9007199254740993 {
		t.Fatalf("AsInt = %d, want 9007199254740993", got)
	}
}

// abstract-machine 方言：顶层 symbol_spaces 与 binding_addr 操作数。
func TestLoadReadsSymbolSpacesAndBindingAddr(t *testing.T) {
	text := `{"version":1,"main":0,"symbol_spaces":[` +
		`{"id":0,"name":"Main","parent":null,"slots":[{"symbol":"x","index":0,"source":"define"}]},` +
		`{"id":1,"name":"let:x","parent":0,"slots":[{"symbol":"y","index":0,"source":"let"}]}],` +
		`"functions":[{"name":"<main>","params":[],"register_count":2,"instructions":[` +
		`{"opcode":"SLOT_COMPLETE","operands":[` +
		`{"type":"binding_addr","value":{"space":1,"slot":0}},{"type":"int","value":1}]}]}]}`
	prog, err := Load([]byte(text))
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	if len(prog.SymbolSpaces) != 2 {
		t.Fatalf("symbol_spaces = %+v", prog.SymbolSpaces)
	}
	if prog.SymbolSpaces[0].Parent != nil {
		t.Fatalf("root parent = %v, want nil", prog.SymbolSpaces[0].Parent)
	}
	if prog.SymbolSpaces[1].Parent == nil || *prog.SymbolSpaces[1].Parent != 0 {
		t.Fatalf("child parent = %v, want 0", prog.SymbolSpaces[1].Parent)
	}
	operand := prog.Functions[0].Instructions[0].Operands[0]
	address, ok := operand.AsBindingAddr()
	if !ok || address.Space != 1 || address.Slot != 0 {
		t.Fatalf("binding_addr = %+v (%v)", address, ok)
	}
}
