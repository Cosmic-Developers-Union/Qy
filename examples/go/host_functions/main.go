// 示例 2：宿主语言扩展 —— 用 Go 写算子，注册进 Qy 虚拟机。
//
//	go run ./examples/go/host_functions
//
// 演示：`Env.Define` 注册纯算子 / 同名覆盖标准算子 / 接管 Qy 输出 /
// 注入宿主常量。详见 `examples/go/qyhost/qyhost.go::RunHostFunctions` 的注释。
package main

import (
	"fmt"
	"os"

	"github.com/Cosmic-Developers-Union/Qy/examples/go/qyhost"
)

func main() {
	if err := qyhost.RunHostFunctions(os.Stdout); err != nil {
		fmt.Fprintf(os.Stderr, "host_functions: %v\n", err)
		os.Exit(1)
	}
}
