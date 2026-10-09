# coding: utf-8
"""示例目录的可运行性守卫。.

`examples/` 按宿主语言分目录（见 `docs/examples.md`）：`qy/` 是 Qy 源码、`py/` 是
Python 宿主示例、`ts/` 是 TypeScript 宿主示例。这些示例是文档之外的"活样例"，
必须始终可运行，否则会随实现演进而腐化。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_EXAMPLES = _REPO_ROOT / "examples"

requires_bun = pytest.mark.skipif(shutil.which("bun") is None, reason="needs bun")
requires_go = pytest.mark.skipif(shutil.which("go") is None, reason="needs go")


def _run(command: list[str], env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


@pytest.mark.parametrize(
    "script",
    ["run_validation.py", "inject_symbol_space.py", "bytecode_demo.py"],
)
def test_python_examples_run(script: str):
    result = _run([sys.executable, str(_EXAMPLES / "py" / script)])

    assert result.returncode == 0, f"{script} failed:\n{result.stdout}\n{result.stderr}"


def test_qy_example_tree_is_organized_by_host_language():
    assert (_EXAMPLES / "qy" / "hello.qy").is_file()
    assert (_EXAMPLES / "qy" / "validation").is_dir()
    assert (_EXAMPLES / "qy" / "design").is_dir()
    assert (_EXAMPLES / "py").is_dir()
    # 顶层不再直接放 .qy / .py 示例
    assert not list(_EXAMPLES.glob("*.qy"))
    assert not list(_EXAMPLES.glob("*.py"))


@requires_bun
def test_typescript_examples_run():
    result = _run(["bun", str(_EXAMPLES / "ts" / "run_all.ts")])

    assert result.returncode == 0, f"ts examples failed:\n{result.stdout}\n{result.stderr}"
    assert "examples/ts:" in result.stdout


@requires_bun
def test_typescript_accepts_hello_golden_file(tmp_path: Path):
    """roadmap: TS 宿主必须完整执行 `examples/qy/hello.qy` 且与 Python 逐字节一致。."""
    bytecode = tmp_path / "hello.json"
    export = _run(
        [sys.executable, "-m", "qy", "export", "examples/qy/hello.qy", "-o", str(bytecode)]
    )
    assert export.returncode == 0, export.stderr

    from_python = _run([sys.executable, "-m", "qy", "run", "examples/qy/hello.qy"])
    assert from_python.returncode == 0, from_python.stderr

    from_ts = _run(["bun", "qy/backend/typescript/bin/qyvm.ts", str(bytecode)])
    assert from_ts.returncode == 0, from_ts.stderr
    # `(this)` / `(slot)` / 算子值都有稳定的 Qy 文本表示（`<symbol-space>` /
    # `<slot>` / `<operator x>`），因此 golden file 现在必须逐字节一致。
    assert from_ts.stdout == from_python.stdout


@requires_go
def test_go_accepts_hello_golden_file(tmp_path: Path):
    """roadmap: Go 宿主同样必须完整执行 `examples/qy/hello.qy` 且与 Python 逐字节一致。."""
    bytecode = tmp_path / "hello.json"
    export = _run(
        [sys.executable, "-m", "qy", "export", "examples/qy/hello.qy", "-o", str(bytecode)]
    )
    assert export.returncode == 0, export.stderr

    from_python = _run([sys.executable, "-m", "qy", "run", "examples/qy/hello.qy"])
    assert from_python.returncode == 0, from_python.stderr

    env = {**os.environ, "GOCACHE": str(tmp_path / "gocache")}
    from_go = _run(["go", "run", "./qy/backend/golang/cmd/qyvm", str(bytecode)], env=env)
    assert from_go.returncode == 0, from_go.stderr
    assert from_go.stdout == from_python.stdout
