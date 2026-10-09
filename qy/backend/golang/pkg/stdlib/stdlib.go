// Package stdlib 装配 Qy 标准 profile：标准运行环境、CALL_BUILTIN ABI 表、
// 以及模块注册表。
//
// 真源：
//   - `qy/std/profile.py` + `qy/std/__init__.py`：标准 profile 只装 `qy.core` + `qy.io`；
//   - `qy/session/pre_ss.py`：literal 层（lisp-ss → number-ss → char-ss → string-ss）；
//   - `qy/core/operator_builtins.py`：CALL_BUILTIN 的下标顺序（跨后端 ABI，不可改）；
//   - `qy/vm/instance/builtins.py`：下标 → 标准实现体。
//
// 本包是 `qy/backend/typescript/src/stdlib/index.ts` 的 Go 同构移植。
package stdlib

import (
	"github.com/Cosmic-Developers-Union/Qy/qy/backend/golang/pkg/bytecode"
	"github.com/Cosmic-Developers-Union/Qy/qy/backend/golang/pkg/vm"
)

// BuiltinNames 是内建算子名（顺序即 ABI 下标），来自
// `qy/core/operator_builtins.py::BUILTIN_OPERATORS`。不得改动顺序。
var BuiltinNames = []string{
	"+",
	"-",
	"*",
	"/",
	"=",
	"eq",
	"<",
	">",
	"display",
	"echo",
	"newline",
	"read",
	"read-int",
	"cons",
	"car",
	"cdr",
	"nil?",
	"not",
}

func echoBody(args []vm.Value) (vm.Value, error) {
	if _, err := PrintOp(args, nil); err != nil {
		return nil, err
	}
	if len(args) == 0 {
		return nil, nil
	}
	return args[len(args)-1], nil
}

// readBody 是宿主 stdin 读取（`read` / `read-int`）：语料不触达，返回 nil 表示无输入。
func readBody(_ []vm.Value) (vm.Value, error) {
	return vm.QyNil, nil
}

// Builtins 返回 CALL_BUILTIN 的实现表（下标与 BuiltinNames 对齐）。
//
// 对应 `qy/vm/instance/builtins.py` 的下标取用。
func Builtins() []vm.BuiltinFunc {
	return []vm.BuiltinFunc{
		func(args []vm.Value) (vm.Value, error) { return Add(args...) },
		func(args []vm.Value) (vm.Value, error) { return Sub(args...) },
		func(args []vm.Value) (vm.Value, error) { return Mul(args...) },
		func(args []vm.Value) (vm.Value, error) { return Div(args...) },
		func(args []vm.Value) (vm.Value, error) { return NumEq(args[0], args[1]) },
		func(args []vm.Value) (vm.Value, error) { return Eq(args[0], args[1]) },
		func(args []vm.Value) (vm.Value, error) { return Lt(args...) },
		func(args []vm.Value) (vm.Value, error) { return Gt(args...) },
		echoBody,
		echoBody,
		func([]vm.Value) (vm.Value, error) { return NewlineOp() },
		readBody,
		readBody,
		func(args []vm.Value) (vm.Value, error) { return ConsOp(args[0], args[1]) },
		func(args []vm.Value) (vm.Value, error) { return CarOp(args[0]) },
		func(args []vm.Value) (vm.Value, error) { return CdrOp(args[0]) },
		func(args []vm.Value) (vm.Value, error) { return NilPredicate(args[0]) },
		func(args []vm.Value) (vm.Value, error) { return NotOp(args[0]) },
	}
}

// CreateStandardEnvironment 建立标准运行环境。
//
// 链布局（自上而下 = 解析顺序）：
//
//	qy.io → qy.core → number-ss → lisp-ss
//
// 全链 miss 之后才走字面量解析（number/char/string/T/nil/none），与
// `RuntimeSpace.resolve` + `ProfileConfig.resolve_literal` 的行为一致。
func CreateStandardEnvironment() *vm.Env {
	lisp := vm.NewNamedEnv(nil, "lisp-ss")
	lisp.Define("T", vm.QyT)
	lisp.Define("nil", vm.QyNil)
	lisp.Define("true", vm.QyT)
	lisp.Define("false", vm.QyNil)
	lisp.Define("none", vm.QyNone)

	numbers := vm.NewNamedEnv(lisp, "number-ss")
	installEager(numbers, map[string]func(args []vm.Value) (vm.Value, error){
		"=":              func(args []vm.Value) (vm.Value, error) { return NumEq(args[0], args[1]) },
		"==":             func(args []vm.Value) (vm.Value, error) { return PyEq(args[0], args[1]) },
		"+":              func(args []vm.Value) (vm.Value, error) { return Add(args...) },
		"-":              func(args []vm.Value) (vm.Value, error) { return Sub(args...) },
		"*":              func(args []vm.Value) (vm.Value, error) { return Mul(args...) },
		"/":              func(args []vm.Value) (vm.Value, error) { return Div(args...) },
		"mod":            func(args []vm.Value) (vm.Value, error) { return Mod(args...) },
		"<":              func(args []vm.Value) (vm.Value, error) { return Lt(args...) },
		">":              func(args []vm.Value) (vm.Value, error) { return Gt(args...) },
		"<=":             func(args []vm.Value) (vm.Value, error) { return Le(args...) },
		">=":             func(args []vm.Value) (vm.Value, error) { return Ge(args...) },
		"string->number": func(args []vm.Value) (vm.Value, error) { return StringToNumber(args[0]) },
		"number?":        func(args []vm.Value) (vm.Value, error) { return NumberP(args[0]), nil },
		"remainder":      func(args []vm.Value) (vm.Value, error) { return Remainder(args...) },
	})

	core := vm.NewNamedEnv(numbers, "qy.core")
	installEager(core, DataBindings())
	installEager(core, ControlBindings())
	installRaw(core, map[string]func(args []vm.Value, env vm.Value) (vm.Value, error){
		"reify": ReifyOp,
		"this":  ThisOp,
		"slot":  SlotOp,
		"bind":  BindOp,
	})

	io := vm.NewNamedEnv(core, "qy.io")
	installRaw(io, IOBindings())

	// 顶层可写 head（对应 Python 的 `pre-ssc-head`）：顶层 define / from fold 落在
	// 这一层，不会与 qy.io 模块自身的绑定冲突。
	return io.Child()
}

type eagerBindings = map[string]func(args []vm.Value) (vm.Value, error)
type rawBindings = map[string]func(args []vm.Value, env vm.Value) (vm.Value, error)

func installEager(env *vm.Env, bindings eagerBindings) {
	for name, fn := range bindings {
		env.Define(name, &vm.PureOperator{Name: name, Fn: fn})
	}
}

func installRaw(env *vm.Env, bindings rawBindings) {
	for name, fn := range bindings {
		env.Define(name, &vm.RawOperator{Name: name, Fn: fn})
	}
}

// ---------------------------------------------------------------------------
// 模块注册表（安装到 VM 实例）
// ---------------------------------------------------------------------------

// RegisterBuiltinModules 把内置模块（qy.core / qy.io / qy.num / qy.str）
// 安装进 VM 实例的模块注册表。对应 `qy/std/__init__.py` 的模块 loader 注册表。
func RegisterBuiltinModules(machine *vm.VM) {
	for name, module := range BuiltinModules() {
		machine.Modules[name] = module
	}
}

// BuiltinModules 构造内置模块表。
func BuiltinModules() map[string]*vm.ModuleValue {
	modules := map[string]*vm.ModuleValue{}

	coreExports := map[string]vm.Value{}
	for name, fn := range DataBindings() {
		coreExports[name] = &vm.PureOperator{Name: name, Fn: fn}
	}
	for name, fn := range ControlBindings() {
		coreExports[name] = &vm.PureOperator{Name: name, Fn: fn}
	}
	coreExports["reify"] = &vm.RawOperator{Name: "reify", Fn: ReifyOp}
	coreExports["this"] = &vm.RawOperator{Name: "this", Fn: ThisOp}
	coreExports["slot"] = &vm.RawOperator{Name: "slot", Fn: SlotOp}
	coreExports["bind"] = &vm.RawOperator{Name: "bind", Fn: BindOp}
	modules["qy.core"] = vm.NewModuleValue("qy.core", coreExports)

	ioExports := map[string]vm.Value{}
	for name, fn := range IOBindings() {
		ioExports[name] = &vm.RawOperator{Name: name, Fn: fn}
	}
	modules["qy.io"] = vm.NewModuleValue("qy.io", ioExports)

	numberExports := map[string]vm.Value{}
	for name, fn := range map[string]func(args []vm.Value) (vm.Value, error){
		"=":              func(args []vm.Value) (vm.Value, error) { return NumEq(args[0], args[1]) },
		"==":             func(args []vm.Value) (vm.Value, error) { return PyEq(args[0], args[1]) },
		"+":              func(args []vm.Value) (vm.Value, error) { return Add(args...) },
		"-":              func(args []vm.Value) (vm.Value, error) { return Sub(args...) },
		"*":              func(args []vm.Value) (vm.Value, error) { return Mul(args...) },
		"/":              func(args []vm.Value) (vm.Value, error) { return Div(args...) },
		"mod":            func(args []vm.Value) (vm.Value, error) { return Mod(args...) },
		"<":              func(args []vm.Value) (vm.Value, error) { return Lt(args...) },
		">":              func(args []vm.Value) (vm.Value, error) { return Gt(args...) },
		"<=":             func(args []vm.Value) (vm.Value, error) { return Le(args...) },
		">=":             func(args []vm.Value) (vm.Value, error) { return Ge(args...) },
		"string->number": func(args []vm.Value) (vm.Value, error) { return StringToNumber(args[0]) },
		"number?":        func(args []vm.Value) (vm.Value, error) { return NumberP(args[0]), nil },
		"remainder":      func(args []vm.Value) (vm.Value, error) { return Remainder(args...) },
	} {
		numberExports[name] = &vm.PureOperator{Name: name, Fn: fn}
	}
	modules["qy.num"] = vm.NewModuleValue("qy.num", numberExports)

	stringExports := map[string]vm.Value{}
	for name, fn := range StringBindings() {
		stringExports[name] = &vm.PureOperator{Name: name, Fn: fn}
	}
	modules["qy.str"] = vm.NewModuleValue("qy.str", stringExports)

	charExports := map[string]vm.Value{}
	for name, fn := range charBindings() {
		charExports[name] = &vm.PureOperator{Name: name, Fn: fn}
	}
	modules["qy.char"] = vm.NewModuleValue("qy.char", charExports)

	// 具体数值空间（qy.int8..qy.float128）。
	for name, module := range NumberSpaceModules() {
		modules[name] = module
	}

	return modules
}

// NewMachine 是宿主最常用的装配入口：装载程序、建立标准环境、注册内置模块与
// CALL_BUILTIN ABI 表。
func NewMachine(program *bytecode.Program) (*vm.VM, error) {
	env := CreateStandardEnvironment()
	machine, err := vm.NewVM(program, env)
	if err != nil {
		return nil, err
	}
	machine.Builtins = Builtins()
	RegisterBuiltinModules(machine)
	return machine, nil
}
