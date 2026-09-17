# coding: utf-8
"""Register VM execution of the LIR ``abstract-machine`` dialect.

覆盖：

- ``compile_lir_bytecode`` 接受 ``abstract-machine`` dialect；
- VM 执行显式 handler 栈 / 续延 opcode（``HANDLER_*`` / ``EFFECT_*`` / ``CONT_*`` /
  ``SS_*`` / ``SLOT_COMPLETE``）；
- 与 ``compat`` dialect 的 register VM 结果逐一对比（差分测试）。
"""

from __future__ import annotations

import glob
from pathlib import Path

import pytest

from qy.async_utils import run_coro
from qy.backend.vm.compiler import compile_lir_bytecode
from qy.build.artifact import LIR
from qy.build.pipeline import compile_source_to_kind
from qy.build.pipeline import lir_artifact
from qy.ir.lir import LIRProgram
from qy.passes.pass_base import PipelineOptions
from qy.passes.pass_base import PipelineSession
from qy.session.runtime_space import create_standard_runtime_space
from qy.vm.instance.machine import RegisterVirtualMachine

ROOT = Path(__file__).resolve().parents[1]

_TOLERANT = PipelineOptions(lir_dialect="abstract-machine", error_threshold=10**6)
_TOLERANT_COMPAT = PipelineOptions(lir_dialect="compat", error_threshold=10**6)


def _lir(source: str, dialect: str, env: object) -> LIRProgram:
    options = _TOLERANT if dialect == "abstract-machine" else _TOLERANT_COMPAT
    result = compile_source_to_kind(
        source,
        PipelineSession(env=env),
        kind=LIR,
        options=options,
    )
    return lir_artifact(result)


def _evaluate(source: str, dialect: str) -> object:
    # Compilation and execution must share one Qy instance/env: macro hygiene
    # definition-site bindings live in the compile-time namespace of that env.
    env = create_standard_runtime_space()
    bytecode = compile_lir_bytecode(_lir(source, dialect, env))
    assert bytecode.ok, [d.message for d in bytecode.diagnostics]
    return run_coro(RegisterVirtualMachine(bytecode, env).evaluate())


def test_compiler_accepts_abstract_machine_dialect():
    bytecode = compile_lir_bytecode(
        _lir("(defeffect ask) (perform ask 1)", "abstract-machine", create_standard_runtime_space())
    )
    opcodes = [inst.opcode for fn in bytecode.functions for inst in fn.instructions]
    assert "EFFECT_UNWIND" in opcodes or "CONT_CAPTURE" in opcodes


def test_compiler_rejects_unknown_dialect():
    bytecode = compile_lir_bytecode(LIRProgram((), dialect="bogus"))  # ty: ignore[invalid-argument-type]
    assert not bytecode.ok
    assert any("dialect" in d.message for d in bytecode.diagnostics)


def test_compat_dialect_still_rejects_abstract_machine_opcodes():
    from qy.core.syntax import Symbol
    from qy.ir.lir import LIRFunction
    from qy.ir.lir import LIRInstruction

    program = LIRProgram(
        (
            LIRFunction(
                Symbol("<main>"),
                (),
                1,
                (
                    LIRInstruction("HANDLER_PUSH", (0, 1, None, ())),
                    LIRInstruction("RETURN", (0,)),
                ),
            ),
        ),
        dialect="compat",
    )
    bytecode = compile_lir_bytecode(program)
    assert not bytecode.ok


@pytest.mark.parametrize(
    "source",
    [
        # resume
        """
        (let ()
          (defeffect ask)
          (handle (+ 1 (perform ask 41)) ((ask (arg k) (resume k arg)))))
        """,
        # multi-shot resume
        """
        (let ()
          (defeffect choose)
          (handle
            (+ (perform choose 20) 1)
            ((choose (value k)
              (+ (resume k value) (resume k (+ value 1)))))))
        """,
        # handler that does not resume
        """
        (let ()
          (defeffect stop-here)
          (handle (perform stop-here 42) ((stop-here (value k) value))))
        """,
        # non-resumable effect
        """
        (let ()
          (defeffect abort-now :resumable false)
          (handle (perform abort-now 42) ((abort-now (value k) value))))
        """,
        # nested handlers
        """
        (let ()
          (defeffect outer)
          (defeffect inner)
          (handle
            (handle (perform inner 1)
              ((inner (v k) (resume k (+ v 10)))))
            ((outer (v k) v))))
        """,
    ],
)
def test_abstract_machine_matches_compat_for_effects(source):
    assert _evaluate(source, "abstract-machine") == _evaluate(source, "compat")


def test_abstract_machine_matches_compat_for_examples():
    files = [
        "examples/qy/hello.qy",
        *sorted(glob.glob("examples/qy/validation/*.qy")),
    ]
    for relative in files:
        source = (ROOT / relative).read_text(encoding="utf-8")
        assert _evaluate(source, "abstract-machine") == _evaluate(source, "compat"), relative
