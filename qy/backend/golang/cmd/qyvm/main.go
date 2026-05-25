package main

import (
	"fmt"
	"os"

	"github.com/aspect-build/qy-vm/pkg/bytecode"
	"github.com/aspect-build/qy-vm/pkg/stdlib"
	"github.com/aspect-build/qy-vm/pkg/vm"
)

func main() {
	if len(os.Args) < 2 {
		fmt.Fprintf(os.Stderr, "usage: qyvm <bytecode.json>\n")
		os.Exit(1)
	}

	debug := len(os.Args) > 2 && os.Args[2] == "--debug"

	prog, err := bytecode.LoadFile(os.Args[1])
	if err != nil {
		fmt.Fprintf(os.Stderr, "error: %v\n", err)
		os.Exit(1)
	}

	env := vm.NewSymbolSpace("root", nil)
	stdlib.InstallStdlib(env)

	if prog.HygieneBindings != nil {
		for hygieneName, baseName := range prog.HygieneBindings {
			if val, ok := env.Resolve(baseName); ok {
				env.Define(hygieneName, val)
			}
		}
	}

	machine := vm.NewVM(prog)
	if debug {
		machine.Debug = true
	}
	result, err := machine.Execute(env)
	if err != nil {
		fmt.Fprintf(os.Stderr, "runtime error: %v\n", err)
		os.Exit(1)
	}

	fmt.Println(vm.ValueToString(result))
}
