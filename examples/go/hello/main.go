// 示例 1：把 Qy 程序编成字节码，再用 Go 虚拟机执行（最小嵌入式用法）。
//
//	go run ./examples/go/hello
//
// 说明：编译器（前端 / 中端）目前只有 Python 实现，因此本示例调用
// `uv run --no-sync qy export` 产出跨宿主共享的字节码 JSON；Go 侧只负责
// **执行**（寄存器虚拟机）。
package main

import (
	"fmt"
	"os"

	"github.com/Cosmic-Developers-Union/Qy/examples/go/qyhost"
)

func main() {
	if err := qyhost.RunHello(os.Stdout); err != nil {
		fmt.Fprintf(os.Stderr, "hello: %v\n", err)
		os.Exit(1)
	}
}
