// qyvm 命令行：执行 `qy export` 产出的字节码 JSON。
//
//	go run ./qy/backend/golang/cmd/qyvm prog.json
//	go run ./qy/backend/golang/cmd/qyvm -   # 从 stdin 读取
//
// 输出格式与 `qy run` 完全一致：对每个顶层结果，跳过绑定形式产物，
// 其余按 `qy/display.py::format_value` 打印并换行。
package main

import (
	"fmt"
	"io"
	"os"

	"github.com/Cosmic-Developers-Union/Qy/qy/backend/golang/pkg/bytecode"
	"github.com/Cosmic-Developers-Union/Qy/qy/backend/golang/pkg/stdlib"
	"github.com/Cosmic-Developers-Union/Qy/qy/backend/golang/pkg/vm"
)

func main() {
	if len(os.Args) < 2 {
		fmt.Fprint(os.Stderr, "usage: qyvm <program.json | ->\n")
		os.Exit(2)
	}

	debug := false
	for _, arg := range os.Args[2:] {
		if arg == "--debug" {
			debug = true
		}
	}

	target := os.Args[1]
	var (
		program *bytecode.Program
		err     error
	)
	if target == "-" {
		data, readErr := io.ReadAll(os.Stdin)
		if readErr != nil {
			fmt.Fprintf(os.Stderr, "qyvm: cannot read stdin: %v\n", readErr)
			os.Exit(2)
		}
		program, err = bytecode.Load(data)
	} else {
		program, err = bytecode.LoadFile(target)
	}
	if err != nil {
		fmt.Fprintf(os.Stderr, "qyvm: %v\n", err)
		os.Exit(2)
	}

	machine, err := stdlib.NewMachine(program)
	if err != nil {
		fmt.Fprintf(os.Stderr, "qyvm: %v\n", err)
		os.Exit(1)
	}
	machine.Debug = debug

	results, err := machine.EvaluateProgram()
	if err != nil {
		if signal, ok := err.(*vm.UnhandledEffectError); ok {
			fmt.Fprintf(os.Stderr, "runtime error: unhandled effect: %s\n", signal.Effect)
			os.Exit(1)
		}
		fmt.Fprintf(os.Stderr, "runtime error: %v\n", err)
		os.Exit(1)
	}

	for _, value := range results {
		if vm.IsDefinitionArtifact(value) {
			continue
		}
		fmt.Println(vm.FormatValue(value))
	}
}
