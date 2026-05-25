package stdlib

import (
	"github.com/aspect-build/qy-vm/pkg/vm"
)

func InstallStdlib(env *vm.SymbolSpace) {
	install(env, Arithmetic())
	install(env, Data())
	install(env, Control())
	install(env, IO())
	install(env, Meta())

	env.Define("true", vm.QyT)
	env.Define("false", vm.QyNil)
	env.Define("T", vm.QyT)
	env.Define("nil", vm.QyNil)
	env.Define("none", nil)
}

func install(env *vm.SymbolSpace, bindings map[string]vm.Value) {
	for name, value := range bindings {
		env.Define(name, value)
	}
}
