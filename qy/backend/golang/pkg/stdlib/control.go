package stdlib

import (
	"github.com/aspect-build/qy-vm/pkg/vm"
)

func Control() map[string]vm.Value {
	return map[string]vm.Value{
		"truthy": &vm.HostFunction{Name: "truthy", Fn: truthy},
		"not":    &vm.HostFunction{Name: "not", Fn: not},
	}
}

func truthy(args []vm.Value) (vm.Value, error) {
	if len(args) < 1 {
		return vm.QyNil, nil
	}
	if vm.IsTruthy(args[0]) {
		return vm.QyT, nil
	}
	return vm.QyNil, nil
}

func not(args []vm.Value) (vm.Value, error) {
	if len(args) < 1 {
		return vm.QyT, nil
	}
	if vm.IsTruthy(args[0]) {
		return vm.QyNil, nil
	}
	return vm.QyT, nil
}
