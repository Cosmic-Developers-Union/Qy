package stdlib

import (
	"strings"
	"testing"

	"github.com/Cosmic-Developers-Union/Qy/qy/backend/golang/pkg/bytecode"
	"github.com/Cosmic-Developers-Union/Qy/qy/backend/golang/pkg/vm"
)

// ---------------------------------------------------------------------------
// CALL_BUILTIN ABI
// ---------------------------------------------------------------------------

func TestBuiltinABIOrder(t *testing.T) {
	want := []string{
		"+", "-", "*", "/", "=", "eq", "<", ">",
		"display", "echo", "newline", "read", "read-int",
		"cons", "car", "cdr", "nil?", "not",
	}
	if len(BuiltinNames) != len(want) {
		t.Fatalf("BuiltinNames has %d entries, want %d", len(BuiltinNames), len(want))
	}
	for index, name := range want {
		if BuiltinNames[index] != name {
			t.Errorf("BuiltinNames[%d] = %q, want %q", index, BuiltinNames[index], name)
		}
	}
	if impls := Builtins(); len(impls) != len(want) {
		t.Fatalf("Builtins has %d entries, want %d", len(impls), len(want))
	}
}

func TestCallBuiltinArithmetic(t *testing.T) {
	impls := Builtins()
	value, err := impls[0]([]vm.Value{vm.NewInt(40), vm.NewInt(2)}) // +
	if err != nil {
		t.Fatalf("builtin +: %v", err)
	}
	if vm.FormatValue(value) != "42" {
		t.Fatalf("builtin + = %s", vm.FormatValue(value))
	}
	value, err = impls[13]([]vm.Value{value, vm.QyNil}) // cons
	if err != nil {
		t.Fatalf("builtin cons: %v", err)
	}
	if vm.FormatValue(value) != "(42)" {
		t.Fatalf("builtin cons = %s", vm.FormatValue(value))
	}
}

func TestCallBuiltinDivideByZeroSignalsEffect(t *testing.T) {
	impls := Builtins()
	_, err := impls[3]([]vm.Value{vm.NewInt(1), vm.NewInt(0)}) // /
	if err == nil {
		t.Fatal("expected divide-by-zero effect signal")
	}
	signal, ok := err.(*vm.EffectSignal)
	if !ok {
		t.Fatalf("error = %T, want *vm.EffectSignal", err)
	}
	if signal.Effect != "divide-by-zero" || !signal.Resumable {
		t.Fatalf("signal = %+v", signal)
	}
}

// ---------------------------------------------------------------------------
// 端到端：把内嵌字节码 JSON 跑完整条 VM 路径（不需要 Python / uv）
// ---------------------------------------------------------------------------

// hygiene + CALL_BUILTIN 程序：`(= (+ 40 2) 42)` 风格，并额外 cons 出 (42)。
const hygieneProgram = `{
  "version": 1,
  "main": 0,
  "functions": [
    {
      "name": "<main>",
      "params": [],
      "register_count": 7,
      "instructions": [
        {"opcode": "LOAD_ENV", "operands": [
          {"type": "reg", "value": 0}, {"type": "symbol", "value": "__qy_hygiene_def___1"}]},
        {"opcode": "LOAD_HOST", "operands": [
          {"type": "reg", "value": 1},
          {"type": "int", "class": "IntValue", "value": {"value": {"type": "int", "value": 40}}}]},
        {"opcode": "LOAD_HOST", "operands": [
          {"type": "reg", "value": 2},
          {"type": "int", "class": "IntValue", "value": {"value": {"type": "int", "value": 2}}}]},
        {"opcode": "CALL", "operands": [
          {"type": "reg", "value": 3}, {"type": "reg", "value": 0},
          {"type": "reg_tuple", "value": [1, 2]}]},
        {"opcode": "APPEND_RESULT", "operands": [{"type": "reg", "value": 3}]},
        {"opcode": "LOAD_HOST", "operands": [{"type": "reg", "value": 4}, {"type": "nil"}]},
        {"opcode": "CALL_BUILTIN", "operands": [
          {"type": "reg", "value": 5}, {"type": "int", "value": 13},
          {"type": "tuple", "value": [
            {"type": "int", "value": 3}, {"type": "int", "value": 4}]}]},
        {"opcode": "APPEND_RESULT", "operands": [{"type": "reg", "value": 5}]},
        {"opcode": "RETURN", "operands": [{"type": "reg", "value": 3}]}
      ]
    }
  ],
  "hygiene_bindings": {"__qy_hygiene_def___1": "+"}
}`

func TestHygieneAliasAndCallBuiltin(t *testing.T) {
	program, err := bytecode.Load([]byte(hygieneProgram))
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	machine, err := NewMachine(program)
	if err != nil {
		t.Fatalf("NewMachine: %v", err)
	}
	results, err := machine.EvaluateProgram()
	if err != nil {
		t.Fatalf("EvaluateProgram: %v", err)
	}
	lines := formatLines(results)
	want := []string{"42", "(42)"}
	if strings.Join(lines, "|") != strings.Join(want, "|") {
		t.Fatalf("results = %v, want %v", lines, want)
	}
}

// 模块 + 编译期宏导出：`from M import pub, my-macro`，其中 my-macro 只在
// `module_macro_exports` 里，运行期没有绑定，必须跳过而不是报错。
const moduleProgram = `{
  "version": 1,
  "main": 0,
  "functions": [
    {
      "name": "<main>",
      "params": [],
      "register_count": 6,
      "instructions": [
        {"opcode": "DEFINE_MODULE", "operands": [
          {"type": "int", "value": 0}, {"type": "symbol", "value": "M"},
          {"type": "int", "value": 1}, {"type": "symbol_tuple", "value": ["pub"]}]},
        {"opcode": "APPEND_RESULT", "operands": [{"type": "reg", "value": 0}]},
        {"opcode": "FROM_IMPORT", "operands": [
          {"type": "symbol", "value": "M"},
          {"type": "import_specs", "value": [
            {"name": "pub", "alias": "pub"},
            {"name": "my-macro", "alias": "my-macro"}]}]},
        {"opcode": "LOAD_ENV", "operands": [{"type": "reg", "value": 1}, {"type": "symbol", "value": "="}]},
        {"opcode": "LOAD_ENV", "operands": [{"type": "reg", "value": 2}, {"type": "symbol", "value": "pub"}]},
        {"opcode": "LOAD_HOST", "operands": [
          {"type": "reg", "value": 3},
          {"type": "int", "class": "IntValue", "value": {"value": {"type": "int", "value": 7}}}]},
        {"opcode": "CALL_BUILTIN", "operands": [
          {"type": "reg", "value": 4}, {"type": "int", "value": 4},
          {"type": "tuple", "value": [{"type": "int", "value": 2}, {"type": "int", "value": 3}]}]},
        {"opcode": "APPEND_RESULT", "operands": [{"type": "reg", "value": 4}]},
        {"opcode": "RETURN", "operands": [{"type": "reg", "value": 0}]}
      ]
    },
    {
      "name": "<module-body>",
      "params": [],
      "register_count": 1,
      "instructions": [
        {"opcode": "LOAD_HOST", "operands": [
          {"type": "reg", "value": 0},
          {"type": "int", "class": "IntValue", "value": {"value": {"type": "int", "value": 7}}}]},
        {"opcode": "DEFINE_ONCE", "operands": [{"type": "symbol", "value": "pub"}, {"type": "reg", "value": 0}]},
        {"opcode": "RETURN", "operands": [{"type": "reg", "value": 0}]}
      ]
    }
  ],
  "module_macro_exports": {"M": ["my-macro"]}
}`

func TestFromImportSkipsCompileTimeMacroExport(t *testing.T) {
	program, err := bytecode.Load([]byte(moduleProgram))
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	machine, err := NewMachine(program)
	if err != nil {
		t.Fatalf("NewMachine: %v", err)
	}
	results, err := machine.EvaluateProgram()
	if err != nil {
		t.Fatalf("EvaluateProgram: %v", err)
	}
	lines := formatLines(results)
	if strings.Join(lines, "|") != "T" {
		t.Fatalf("results = %v, want [T]", lines)
	}
}

// 未处理 effect：`(/ 1 0)` 在顶层冒泡。
const unhandledEffectProgram = `{
  "version": 1,
  "main": 0,
  "functions": [
    {
      "name": "<main>",
      "params": [],
      "register_count": 3,
      "instructions": [
        {"opcode": "LOAD_HOST", "operands": [
          {"type": "reg", "value": 0},
          {"type": "int", "class": "IntValue", "value": {"value": {"type": "int", "value": 1}}}]},
        {"opcode": "LOAD_HOST", "operands": [
          {"type": "reg", "value": 1},
          {"type": "int", "class": "IntValue", "value": {"value": {"type": "int", "value": 0}}}]},
        {"opcode": "CALL_BUILTIN", "operands": [
          {"type": "reg", "value": 2}, {"type": "int", "value": 3},
          {"type": "tuple", "value": [{"type": "int", "value": 0}, {"type": "int", "value": 1}]}]},
        {"opcode": "APPEND_RESULT", "operands": [{"type": "reg", "value": 2}]},
        {"opcode": "RETURN", "operands": [{"type": "reg", "value": 2}]}
      ]
    }
  ]
}`

func TestUnhandledEffectIsReported(t *testing.T) {
	program, err := bytecode.Load([]byte(unhandledEffectProgram))
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	machine, err := NewMachine(program)
	if err != nil {
		t.Fatalf("NewMachine: %v", err)
	}
	if _, err := machine.EvaluateProgram(); err == nil {
		t.Fatal("expected unhandled effect error")
	}
}

// HANDLE + PERFORM + RESUME：handler resume 后 body 继续执行。
const effectProgram = `{
  "version": 1,
  "main": 0,
  "functions": [
    {
      "name": "<main>",
      "params": [],
      "register_count": 2,
      "instructions": [
        {"opcode": "HANDLE", "operands": [
          {"type": "reg", "value": 0}, {"type": "int", "value": 1},
          {"type": "handler_specs", "value": [{"effect": "my-effect", "handler_fn": 2}]}]},
        {"opcode": "APPEND_RESULT", "operands": [{"type": "reg", "value": 0}]},
        {"opcode": "RETURN", "operands": [{"type": "reg", "value": 0}]}
      ]
    },
    {
      "name": "body",
      "params": [],
      "register_count": 3,
      "instructions": [
        {"opcode": "LOAD_HOST", "operands": [{"type": "reg", "value": 0}, {"type": "nil"}]},
        {"opcode": "PERFORM", "operands": [
          {"type": "reg", "value": 1}, {"type": "symbol", "value": "my-effect"},
          {"type": "reg", "value": 0}]},
        {"opcode": "RETURN", "operands": [{"type": "reg", "value": 1}]}
      ]
    },
    {
      "name": "handler",
      "params": ["arg", "k"],
      "register_count": 3,
      "instructions": [
        {"opcode": "LOAD_ENV", "operands": [{"type": "reg", "value": 0}, {"type": "symbol", "value": "k"}]},
        {"opcode": "LOAD_HOST", "operands": [
          {"type": "reg", "value": 1},
          {"type": "int", "class": "IntValue", "value": {"value": {"type": "int", "value": 5}}}]},
        {"opcode": "RESUME", "operands": [
          {"type": "reg", "value": 2}, {"type": "reg", "value": 0}, {"type": "reg", "value": 1}]},
        {"opcode": "RETURN", "operands": [{"type": "reg", "value": 2}]}
      ]
    }
  ]
}`

func TestPerformAndResume(t *testing.T) {
	program, err := bytecode.Load([]byte(effectProgram))
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	machine, err := NewMachine(program)
	if err != nil {
		t.Fatalf("NewMachine: %v", err)
	}
	results, err := machine.EvaluateProgram()
	if err != nil {
		t.Fatalf("EvaluateProgram: %v", err)
	}
	lines := formatLines(results)
	if strings.Join(lines, "|") != "5" {
		t.Fatalf("results = %v, want [5]", lines)
	}
}

func formatLines(results []vm.Value) []string {
	lines := []string{}
	for _, value := range results {
		if vm.IsDefinitionArtifact(value) {
			continue
		}
		lines = append(lines, vm.FormatValue(value))
	}
	return lines
}
