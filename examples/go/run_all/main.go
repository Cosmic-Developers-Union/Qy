// 示例入口：一次运行全部 Go 宿主示例（对应 `examples/ts/run_all.ts`）。
//
//	go run ./examples/go/run_all
//
// 需要 `uv`（编译器在 Python 侧）与 `go`。
package main

import (
	"fmt"
	"os"

	"github.com/Cosmic-Developers-Union/Qy/examples/go/qyhost"
)

func main() {
	failed := false

	fmt.Println("=== examples/go/hello ===")
	if err := qyhost.RunHello(os.Stdout); err != nil {
		fmt.Fprintf(os.Stderr, "hello: %v\n", err)
		failed = true
	}

	fmt.Println("")
	fmt.Println("=== examples/go/host_functions ===")
	if err := qyhost.RunHostFunctions(os.Stdout); err != nil {
		fmt.Fprintf(os.Stderr, "host_functions: %v\n", err)
		failed = true
	}

	if failed {
		os.Exit(1)
	}
}
