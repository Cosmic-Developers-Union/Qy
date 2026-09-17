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
