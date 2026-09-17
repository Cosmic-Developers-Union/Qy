package vm

import (
	"testing"

	"github.com/Cosmic-Developers-Union/Qy/qy/backend/golang/pkg/bytecode"
)

// 交换格式的大整数解码必须精确（不能经 float64 中转）。
func TestDecodeExactBigIntConstant(t *testing.T) {
	text := `{"version":1,"main":0,"functions":[{"name":"<main>","params":[],` +
		`"register_count":1,"instructions":[` +
		`{"opcode":"LOAD_HOST","operands":[{"type":"reg","value":0},` +
		`{"type":"int","class":"IntValue","value":{"value":{"type":"int","value":9007199254740993}}}]},` +
		`{"opcode":"RETURN","operands":[{"type":"reg","value":0}]}]}]}`
	program, err := bytecode.Load([]byte(text))
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	functions, err := decodeFunctions(program)
	if err != nil {
		t.Fatalf("decodeFunctions: %v", err)
	}
	operand := functions[0].Instructions[0].Operands[1]
	number, ok := operand.(*Number)
	if !ok {
		t.Fatalf("operand = %T, want *Number", operand)
	}
	if got := number.BigPayload().String(); got != "9007199254740993" {
		t.Fatalf("decoded int = %s, want 9007199254740993", got)
	}
	if got := FormatValue(number); got != "9007199254740993" {
		t.Fatalf("FormatValue = %s", got)
	}
}

// abstract-machine 方言：SLOT_COMPLETE 把 BindingAddr 还原成 Symbol 再 define_once。
const slotCompleteProgram = `{
  "version": 1,
  "main": 0,
  "symbol_spaces": [
    {"id": 0, "name": "Main", "parent": null,
     "slots": [{"symbol": "x", "index": 0, "source": "define"}]}
  ],
  "functions": [
    {
      "name": "<main>",
      "params": [],
      "register_count": 2,
      "instructions": [
        {"opcode": "LOAD_HOST", "operands": [
          {"type": "reg", "value": 0},
          {"type": "int", "class": "IntValue", "value": {"value": {"type": "int", "value": 7}}}]},
        {"opcode": "SLOT_COMPLETE", "operands": [
          {"type": "binding_addr", "value": {"space": 0, "slot": 0}},
          {"type": "int", "value": 0}]},
        {"opcode": "LOAD_ENV", "operands": [
          {"type": "reg", "value": 1}, {"type": "symbol", "value": "x"}]},
        {"opcode": "APPEND_RESULT", "operands": [{"type": "reg", "value": 1}]},
        {"opcode": "RETURN", "operands": [{"type": "reg", "value": 1}]}
      ]
    }
  ]
}`

func TestSlotCompleteDefinesFromLayout(t *testing.T) {
	program, err := bytecode.Load([]byte(slotCompleteProgram))
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	if len(program.SymbolSpaces) != 1 || program.SymbolSpaces[0].Slots[0].Symbol != "x" {
		t.Fatalf("symbol_spaces = %+v", program.SymbolSpaces)
	}
	machine, err := NewVM(program, nil)
	if err != nil {
		t.Fatalf("NewVM: %v", err)
	}
	results, err := machine.EvaluateProgram()
	if err != nil {
		t.Fatalf("EvaluateProgram: %v", err)
	}
	if len(results) != 1 || FormatValue(results[0]) != "7" {
		t.Fatalf("results = %v", results)
	}
}

// 没有 layout 的 compat 方言里，SLOT_COMPLETE 是 no-op（同 Python 返回 None）。
func TestSlotCompleteWithoutLayoutIsNoop(t *testing.T) {
	text := `{"version":1,"main":0,"functions":[{"name":"<main>","params":[],` +
		`"register_count":2,"instructions":[` +
		`{"opcode":"LOAD_HOST","operands":[{"type":"reg","value":0},{"type":"int","class":"IntValue","value":{"value":{"type":"int","value":1}}}]},` +
		`{"opcode":"SLOT_COMPLETE","operands":[{"type":"binding_addr","value":{"space":0,"slot":0}},{"type":"int","value":0}]},` +
		`{"opcode":"LOAD_HOST","operands":[{"type":"reg","value":1},{"type":"int","class":"IntValue","value":{"value":{"type":"int","value":2}}}]},` +
		`{"opcode":"RETURN","operands":[{"type":"reg","value":1}]}]}]}`
	program, err := bytecode.Load([]byte(text))
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	machine, err := NewVM(program, nil)
	if err != nil {
		t.Fatalf("NewVM: %v", err)
	}
	if _, err := machine.EvaluateProgram(); err != nil {
		t.Fatalf("EvaluateProgram: %v", err)
	}
}
