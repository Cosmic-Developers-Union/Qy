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

// qyErrorCode 把宿主错误映射为与 Python `qy/errors` 一致的 `QY_*` 代码。
func qyErrorCode(err error) string {
	switch err.(type) {
	case *vm.UnhandledEffectError:
		return "QY_UNHANDLED_EFFECT"
	case *vm.TypeError:
		return "QY_TYPE_ERROR"
	case *vm.ArityError:
		return "QY_ARITY_ERROR"
	case *vm.ResolveError:
		return "QY_UNBOUND_SYMBOL"
	case *vm.ReifyError:
		return "QY_REIFY_ERROR"
	case *vm.AggregateError:
		return "QY_AGGREGATE_ERROR"
	case *vm.EffectError:
		return "QY_EFFECT_ERROR"
	case *vm.RuntimeError:
		return "QY_RUNTIME_ERROR"
	case *vm.EvaluationError:
		return "QY_EVALUATION_ERROR"
	default:
		return "QY_ERROR"
	}
}

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
			fmt.Fprintf(os.Stderr, "%s: unhandled effect '%s'\n", qyErrorCode(err), signal.Effect)
			os.Exit(1)
		}
		fmt.Fprintf(os.Stderr, "%s: %v\n", qyErrorCode(err), err)
		os.Exit(1)
	}

	for _, value := range results {
		if vm.IsDefinitionArtifact(value) {
			continue
		}
		fmt.Println(vm.FormatValue(value))
	}
}
