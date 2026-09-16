# coding: utf-8
"""WebAssembly backend tests.

覆盖：

- LIR -> WAT 的结构（module/table/elem/builtin trampoline）；
- 不支持的 opcode 抛出 :class:`WasmUnsupportedError`；
- 端到端：WAT -> ``wat2wasm`` -> Node WebAssembly 执行，结果与 register VM 一致。

端到端用例在缺少 ``wat2wasm`` 或 ``node`` 时自动跳过。
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from qy.backend.wasm.emit import WasmUnsupportedError
from qy.backend.wasm.emit import emit
from qy.build.artifact import LIR
from qy.build.pipeline import compile_source_to_kind
from qy.build.pipeline import lir_artifact
from qy.passes.pass_base import PipelineSession
from qy.session.runtime_space import create_standard_runtime_space

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_JS = ROOT / "qy" / "resources" / "wasm" / "runtime.js"

_WAT2WASM = shutil.which("wat2wasm")
_NODE = shutil.which("node")

requires_toolchain = pytest.mark.skipif(
    _WAT2WASM is None or _NODE is None,
    reason="needs wat2wasm and node",
)


def _compile_lir(source: str):
    result = compile_source_to_kind(
        source, PipelineSession(env=create_standard_runtime_space()), kind=LIR
    )
    return lir_artifact(result)


def _run_wasm(source: str, tmp_path: Path) -> str:
    wat2wasm = _WAT2WASM
    node = _NODE
    assert wat2wasm is not None and node is not None
    lir = _compile_lir(source)
    wat = emit(lir)
    wat_path = tmp_path / "program.wat"
    wasm_path = tmp_path / "program.wasm"
    wat_path.write_text(wat, encoding="utf-8")
    subprocess.run(
        [wat2wasm, str(wat_path), "-o", str(wasm_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    completed = subprocess.run(
        [node, str(RUNTIME_JS), str(wasm_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout


def test_wasm_emit_structure_for_arithmetic():
    lir = _compile_lir("(+ (* 6 7) 0)")
    wat = emit(lir)

    assert wat.startswith("(module")
    assert '(import "qy" "call_builtin"' in wat
    assert "$qy_fn_0" in wat
    assert '(export "main" (func $qy_fn_0))' in wat
    assert "(table " in wat
    assert "(elem (i32.const 0)" in wat
    # 6 encoded as (6<<3)|int-tag, 7 as (7<<3)
    assert "(i64.const 48)" in wat
    assert "(i64.const 56)" in wat


def test_wasm_emit_rejects_effects():
    lir = _compile_lir("(defeffect ask)")
    with pytest.raises(WasmUnsupportedError):
        emit(lir)


def test_wasm_emit_rejects_non_compat_dialect():
    from qy.ir.lir import LIRProgram

    with pytest.raises(WasmUnsupportedError):
        emit(LIRProgram((), dialect="abstract-machine"))


def test_wasm_unsupported_symbol_raises():
    """A symbol that is neither local, literal, nor builtin must not resolve silently."""
    from qy.core.syntax import Symbol
    from qy.ir.lir import LIRFunction
    from qy.ir.lir import LIRInstruction
    from qy.ir.lir import LIRProgram

    lir = LIRProgram(
        (
            LIRFunction(
                Symbol("<main>"),
                (),
                1,
                (
                    LIRInstruction("LOAD_ENV", (0, Symbol("mystery"))),
                    LIRInstruction("RETURN", (0,)),
                ),
            ),
        )
    )
    with pytest.raises(WasmUnsupportedError):
        emit(lir)


@requires_toolchain
@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("(+ (* 6 7) 0)", "42\n"),
        ("(let ((+ (lambda (left right) left))) (+ 42 0))", "42\n"),
        (
            """
            (let ()
              (defun sum-to (n acc)
                (cond
                  ((= n 0) acc)
                  (true (sum-to (- n 1) (+ acc n)))))
              (sum-to 300 0))
            """,
            "45150\n",
        ),
    ],
)
def test_wasm_matches_register_vm(tmp_path, source, expected):
    assert _run_wasm(source, tmp_path) == expected


@requires_toolchain
def test_wasm_cli_emits_wat(tmp_path):
    from click.testing import CliRunner

    from qy.cli._app import build_cli

    source_path = tmp_path / "program.qy"
    source_path.write_text("(+ 1 2)", encoding="utf-8")
    result = CliRunner().invoke(build_cli(), ["wasm", str(source_path)])

    assert result.exit_code == 0, result.output
    assert result.output.startswith("(module")


@requires_toolchain
def test_wasm_cli_reports_unsupported(tmp_path):
    from click.testing import CliRunner

    from qy.cli._app import build_cli

    source_path = tmp_path / "effects.qy"
    source_path.write_text("(defeffect ask)", encoding="utf-8")
    result = CliRunner().invoke(build_cli(), ["wasm", str(source_path)])

    assert result.exit_code == 1
    assert "not supported by the wasm backend" in result.output
