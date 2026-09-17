# coding: utf-8
"""示例目录的可运行性守卫。.

`examples/` 按宿主语言分目录（见 `docs/examples.md`）：`qy/` 是 Qy 源码、`py/` 是
Python 宿主示例、`ts/` 是 TypeScript 宿主示例。这些示例是文档之外的"活样例"，
必须始终可运行，否则会随实现演进而腐化。
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_EXAMPLES = _REPO_ROOT / "examples"

requires_bun = pytest.mark.skipif(shutil.which("bun") is None, reason="needs bun")


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
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
