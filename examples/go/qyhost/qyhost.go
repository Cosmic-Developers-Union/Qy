// Package qyhost 是 Go 宿主示例共用的工具。
//
// 两个职责：
//  1. `CompileWithQy()`：调用 Python 侧的 `qy export` 生成字节码 JSON（编译器只有
//     Python 实现；Go 宿主只执行字节码）；
//  2. 共用常量与示例入口（`RunHello` / `RunHostFunctions`），供
//     `examples/go/hello`、`examples/go/host_functions`、`examples/go/run_all` 复用。
package qyhost

import (
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"

	"github.com/Cosmic-Developers-Union/Qy/qy/backend/golang/pkg/bytecode"
	"github.com/Cosmic-Developers-Union/Qy/qy/backend/golang/pkg/stdlib"
	"github.com/Cosmic-Developers-Union/Qy/qy/backend/golang/pkg/vm"
)

// DefaultProgram 是默认示例程序：宿主前置算术（返回 42）。
const DefaultProgram = "examples/qy/validation/00_host_arithmetic.qy"

// HostPrintProgram 是宿主扩展示例程序：调用 `print`（宿主可覆盖它）。
const HostPrintProgram = "examples/qy/host_print.qy"

// RepoRoot 返回仓库根目录（examples/go/qyhost/ 的上三级）。
func RepoRoot() (string, error) {
	_, thisFile, _, ok := runtime.Caller(0)
	if !ok {
		return "", fmt.Errorf("cannot locate qyhost package source")
	}
	return filepath.Clean(filepath.Join(filepath.Dir(thisFile), "..", "..", "..")), nil
}

// CompileWithQy 用 `qy export` 把 Qy 源码编译成字节码 JSON，返回临时文件路径。
//
// 注意本工作区 uv 默认缓存只读，因此显式指定 `UV_CACHE_DIR`。
func CompileWithQy(programPath string) (string, error) {
	root, err := RepoRoot()
	if err != nil {
		return "", err
	}
	outDir, err := os.MkdirTemp("", "qy-go-example-")
	if err != nil {
		return "", err
	}
	outPath := filepath.Join(outDir, "program.json")

	command := exec.Command("uv", "run", "--no-sync", "qy", "export", programPath, "-o", outPath)
	command.Dir = root
	command.Env = append(os.Environ(), "UV_CACHE_DIR=/tmp/uv-cache")
	output, err := command.CombinedOutput()
	if err != nil {
		return "", fmt.Errorf("qy export failed for %s:\n%s", programPath, output)
	}
	return outPath, nil
}

// LoadMachine 装载字节码文件并装配标准环境。
func LoadMachine(path string) (*vm.VM, error) {
	program, err := bytecode.LoadFile(path)
	if err != nil {
		return nil, err
	}
	return stdlib.NewMachine(program)
}

// RunLines 执行程序并返回 `qy run` 会打印的文本行（跳过绑定形式产物）。
func RunLines(machine *vm.VM) ([]string, error) {
	results, err := machine.EvaluateProgram()
	if err != nil {
		return nil, err
	}
	lines := []string{}
	for _, value := range results {
		if vm.IsDefinitionArtifact(value) {
			continue
		}
		lines = append(lines, vm.FormatValue(value))
	}
	return lines, nil
}

// ExpectEqual 是示例里用的极简断言。
func ExpectEqual(actual, expected, label string) error {
	if actual != expected {
		return fmt.Errorf("%s: expected %q, got %q", label, expected, actual)
	}
	return nil
}

// RunHello 是示例 1：把 Qy 程序编成字节码，再用 Go 虚拟机执行（最小嵌入式用法）。
func RunHello(out io.Writer) error {
	bytecodePath, err := CompileWithQy(DefaultProgram)
	if err != nil {
		return err
	}
	machine, err := LoadMachine(bytecodePath)
	if err != nil {
		return err
	}
	lines, err := RunLines(machine)
	if err != nil {
		return err
	}
	fmt.Fprintf(out, "程序：%s\n", DefaultProgram)
	fmt.Fprintf(out, "字节码：%s\n", bytecodePath)
	for _, line := range lines {
		fmt.Fprintln(out, line)
	}
	if err := ExpectEqual(strings.Join(lines, "|"), "42", "hello 输出"); err != nil {
		return err
	}
	return nil
}

// RunHostFunctions 是示例 2：宿主语言扩展 —— 用 Go 写算子，注册进 Qy 虚拟机。
//
// 演示三件事：
//  1. `machine.Env.Define(name, &vm.PureOperator{...})`：把 Go 函数注册成 Qy 纯算子
//     （参数与返回值都是 Qy 语义值，用 vm 包的构造器包装）；
//  2. 宿主注册**同名算子会覆盖**标准 profile 的实现（这里覆盖 `display` / `print`），
//     说明宿主扩展在运行时对语言可见；同时演示宿主接管 Qy 的输出
//     （`stdlib.SetOutputWriter`）；
//  3. `machine.Env.Define(name, value)`：宿主向 Qy 环境注入常量。
//
// 重要约束：编译器在**编译期**解析符号，所以程序里出现的名字必须在编译期可解析
// （标准 profile 或 `from` 导入）。因此本示例覆盖 `print` 而不是引入全新名字；
// 若要引入全新算子，需要让编译期环境也知道该名字（例如 Python 侧先注册占位再导出）。
func RunHostFunctions(out io.Writer) error {
	bytecodePath, err := CompileWithQy(HostPrintProgram)
	if err != nil {
		return err
	}

	// 1) 标准 profile 的 print
	plain, err := captureOutput(func(machine *vm.VM) error {
		lines, runErr := RunLines(machine)
		if runErr != nil {
			return runErr
		}
		fmt.Fprintf(out, "标准 print 输出行：%s\n", strings.Join(lines, " | "))
		return nil
	}, bytecodePath)
	if err != nil {
		return err
	}
	if !strings.HasPrefix(plain, "42") {
		return fmt.Errorf("标准 print 输出异常: %q", plain)
	}

	// 2) 宿主覆盖 print：Go 实现
	seen := []string{}
	hosted, err := captureOutput(func(machine *vm.VM) error {
		machine.Env.Define("print", &vm.PureOperator{
			Name: "print",
			Fn: func(args []vm.Value) (vm.Value, error) {
				if len(args) > 0 {
					seen = append(seen, vm.FormatValue(args[0]))
				}
				return vm.NewString("host-print"), nil
			},
		})
		lines, runErr := RunLines(machine)
		if runErr != nil {
			return runErr
		}
		fmt.Fprintf(out, "宿主 print 返回行：%s\n", strings.Join(lines, " | "))
		return nil
	}, bytecodePath)
	if err != nil {
		return err
	}
	if len(seen) != 1 {
		return fmt.Errorf("宿主 print 应被调用 1 次，实际 %d 次", len(seen))
	}
	if err := ExpectEqual(seen[0], "42", "宿主 print 收到的值"); err != nil {
		return err
	}
	if err := ExpectEqual(hosted, "", "宿主 print 返回 Qy 值，不再直接写 stdout"); err != nil {
		return err
	}

	// 3) 注册新算子 + 注入常量（宿主侧可直接使用；编译期未解析的名字不写进程序）
	machine, err := LoadMachine(bytecodePath)
	if err != nil {
		return err
	}
	machine.Env.Define("host-double", &vm.PureOperator{
		Name: "host-double",
		Fn: func(args []vm.Value) (vm.Value, error) {
			number, ok := args[0].(*vm.Number)
			if !ok {
				return nil, vm.NewTypeError("host-double expects an int")
			}
			return vm.NewInt(number.Val * 2), nil
		},
	})
	machine.Env.Define("host-answer", vm.NewInt(42))

	double, err := machine.Env.Resolve(vm.NewSymbol("host-double"))
	if err != nil {
		return err
	}
	answer, err := machine.Env.Resolve(vm.NewSymbol("host-answer"))
	if err != nil {
		return err
	}
	if _, ok := double.(*vm.PureOperator); !ok {
		return fmt.Errorf("host-double 应注册为纯算子")
	}
	fmt.Fprintf(out, "宿主 print 调用：%s\n", strings.Join(seen, " | "))
	fmt.Fprintf(out, "宿主注入常量 host-answer = %s\n", vm.FormatValue(answer))
	fmt.Fprintf(out, "宿主算子 host-double 已注册：%s\n", "yes")
	return nil
}

// captureOutput 把 Qy 的 stdout 输出收集为字符串，再执行 body。
func captureOutput(body func(machine *vm.VM) error, bytecodePath string) (string, error) {
	var builder strings.Builder
	previous := stdlib.GetOutputWriter()
	stdlib.SetOutputWriter(func(text string) { builder.WriteString(text) })
	defer stdlib.SetOutputWriter(previous)

	machine, err := LoadMachine(bytecodePath)
	if err != nil {
		return "", err
	}
	if err := body(machine); err != nil {
		return "", err
	}
	return builder.String(), nil
}
