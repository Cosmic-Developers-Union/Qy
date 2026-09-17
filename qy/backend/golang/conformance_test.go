package conformance

// Go 宿主一致性（conformance）测试。
//
// 完整对拍需要 Python（`uv run qy run` / `qy export`），因此默认跳过；
// 显式打开时等价于执行 `qy/backend/golang/conformance.sh`：
//
//	QY_GO_CONFORMANCE=1 go test ./qy/backend/golang/ -v
//
// 也可以直接运行更完整的脚本（带 --filter / --verbose）：
//
//	bash qy/backend/golang/conformance.sh --verbose

import (
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"testing"
)

func TestCorpusConformance(t *testing.T) {
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
	script := filepath.Join(filepath.Dir(thisFile), "conformance.sh")

	command := exec.Command("bash", script, "--verbose")
	command.Dir = filepath.Join(filepath.Dir(thisFile), "..", "..", "..")
	command.Env = append(os.Environ(), "UV_CACHE_DIR=/tmp/uv-cache")
	output, err := command.CombinedOutput()
	if err != nil {
		t.Fatalf("conformance failed:\n%s", output)
	}
	t.Logf("%s", output)
}
