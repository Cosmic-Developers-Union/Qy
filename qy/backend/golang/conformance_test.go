package conformance

// Go 宿主一致性（conformance）测试。
//
// 完整对拍需要 Python（`uv run qy run` / `qy export`），因此默认跳过；
// 显式打开时等价于执行 `qy/backend/golang/conformance.sh`（两种方言）与
// `qy/backend/golang/bigint_conformance.sh`：
//
//	QY_GO_CONFORMANCE=1 go test ./qy/backend/golang/ -v
//
// 也可以直接运行更完整的脚本（带 --filter / --verbose / --dialect）：
//
//	bash qy/backend/golang/conformance.sh --verbose
//	bash qy/backend/golang/conformance.sh --dialect abstract-machine

import (
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"testing"
)

// runScript 运行 conformance 脚本，失败时把输出并入测试失败信息。
func runScript(t *testing.T, script string, args ...string) {
	t.Helper()
	if os.Getenv("QY_GO_CONFORMANCE") != "1" {
		t.Skip("set QY_GO_CONFORMANCE=1 to run the Python-vs-Go corpus conformance")
	}
	if _, err := exec.LookPath("uv"); err != nil {
		t.Skipf("uv not available: %v", err)
	}

	_, thisFile, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("cannot locate conformance_test.go")
	}
	path := filepath.Join(filepath.Dir(thisFile), script)

	command := exec.Command("bash", append([]string{path}, args...)...)
	command.Dir = filepath.Join(filepath.Dir(thisFile), "..", "..", "..")
	command.Env = append(os.Environ(), "UV_CACHE_DIR=/tmp/uv-cache")
	output, err := command.CombinedOutput()
	if err != nil {
		t.Fatalf("%s failed:\n%s", script, output)
	}
	t.Logf("%s", output)
}

func TestCorpusConformance(t *testing.T) {
	runScript(t, "conformance.sh", "--verbose")
}

func TestCorpusConformanceAbstractMachine(t *testing.T) {
	runScript(t, "conformance.sh", "--verbose", "--dialect", "abstract-machine")
}

func TestBigIntConformance(t *testing.T) {
	runScript(t, "bigint_conformance.sh", "--verbose")
}
