package stdlib

import (
	"fmt"
	"strings"

	"github.com/aspect-build/qy-vm/pkg/vm"
)

func IO() map[string]vm.Value {
	return map[string]vm.Value{
		"print": &vm.HostFunction{Name: "print", Fn: printOp},
		"echo":  &vm.HostFunction{Name: "echo", Fn: printOp},
	}
}

func printOp(args []vm.Value) (vm.Value, error) {
	parts := make([]string, len(args))
	for i, arg := range args {
		parts[i] = vm.ValueToString(arg)
	}
	fmt.Println(strings.Join(parts, " "))
	if len(args) > 0 {
		return args[len(args)-1], nil
	}
	return vm.QyNil, nil
}
