# coding: utf-8
"""`CALL_BUILTIN` 的 ABI 契约与选择规则测试。.

LIR selection（`lir.select_builtins`）把静态可解析的**纯**内建算子调用降成
`CALL_BUILTIN`；bytecode 只携带内建下标，VM 用 `qy/vm/instance/builtins.py` 取用
语言实现自身的算子体（语义单源在 `qy.std` / `qy.session`）。
"""

from __future__ import annotations

from typing import get_args

import pytest

from qy.backend.vm.bytecode import Opcode as BytecodeOpcode
from qy.backend.vm.spec import OPCODE_TABLE
from qy.build.pipeline import bytecode_artifact
from qy.build.pipeline import compile_source_to_kind
from qy.core.operator_builtins import BUILTIN_NAMES
from qy.core.syntax import Symbol
from qy.passes.pass_base import PipelineOptions
from qy.passes.pass_base import PipelineSession
from qy.session.runtime_space import RuntimeSpace
from qy.session.runtime_space import create_standard_runtime_space

_OPTIONS = PipelineOptions(error_threshold=10**6)


def _bytecode(source: str, *, optimize: bool = False, env: object | None = None):
    session = PipelineSession(env=env if env is not None else create_standard_runtime_space())
    result = compile_source_to_kind(
        source,
        session,
        kind="bytecode",
        options=PipelineOptions(error_threshold=10**6, optimize=optimize),
    )
    assert not [d for d in result.diagnostics if d.severity == "error"], result.diagnostics
    return bytecode_artifact(result)


def _opcodes(program) -> list[str]:
    return [inst.opcode for fn in program.functions for inst in fn.instructions]


def test_bytecode_opcode_literal_is_the_spec_contract():
    """Bytecode 的 Opcode 必须与 spec 的 OPCODE_TABLE 完全一致（不得有第二份列表）。."""
    literal = set(get_args(BytecodeOpcode))

    assert literal == set(OPCODE_TABLE)


def test_dynamic_builtin_call_is_selected():
    program = _bytecode("(let ((x 1)) (+ x 2))")

    assert "CALL_BUILTIN" in _opcodes(program)
    assert "CALL" not in _opcodes(program)


def test_selected_builtin_call_carries_canonical_index():
    program = _bytecode("(let ((x 1)) (+ x 2))")
    calls = [
        inst
        for fn in program.functions
        for inst in fn.instructions
        if inst.opcode == "CALL_BUILTIN"
    ]

    assert calls, "expected a selected CALL_BUILTIN"
    assert calls[0].operands[1] == BUILTIN_NAMES.index("+")


def test_shadowed_operator_is_not_selected():
    program = _bytecode("(let ((+ (lambda (a b) 99))) (+ 1 2))")

    assert "CALL_BUILTIN" not in _opcodes(program)
    assert "CALL" in _opcodes(program)


def test_host_override_is_not_selected():
    """宿主把 + 换成自己的函数时不得降成内建调用。."""
    env = RuntimeSpace({Symbol("+"): (lambda *args: 0)}, create_standard_runtime_space())

    program = _bytecode("(let ((x 1)) (+ x 2))", env=env)

    assert "CALL_BUILTIN" not in _opcodes(program)


def test_effect_operator_is_not_selected():
    """效果/作用域算子的调用约定需要 env，只走通用 CALL。."""
    program = _bytecode("(let ((x 1)) (print x))")

    assert "CALL_BUILTIN" not in _opcodes(program)


def test_arities_must_match_builtin_abi():
    """元数不匹配（例如 (+ a b c)）不得降成 2 元内建调用。."""
    program = _bytecode("(let ((a 1) (b 2) (c 3)) (+ a b c))")

    assert "CALL_BUILTIN" not in _opcodes(program)


def test_selected_builtin_calls_evaluate_correctly():
    from qy.async_utils import run_coro
    from qy.vm.instance.machine import RegisterVirtualMachine

    env = create_standard_runtime_space()
    program = _bytecode("(let ((x 40)) (+ x 2))", env=env)
    outcome = run_coro(RegisterVirtualMachine(program, env).evaluate_program())

    assert [str(value) for value in outcome] == ["42"]


def test_call_builtin_rejects_unknown_index():
    from qy.errors import QyRuntimeError
    from qy.vm.instance.builtins import call_builtin

    with pytest.raises(QyRuntimeError):
        call_builtin(10_000, ())


def test_lir_verifier_rejects_bad_builtin_index():
    from qy.ir.lir import LIRFunction
    from qy.ir.lir import LIRInstruction
    from qy.ir.lir import LIRProgram
    from qy.ir.lir import verify_lir

    function = LIRFunction(
        name=Symbol("<main>"),
        params=(),
        register_count=2,
        instructions=(
            LIRInstruction("LOAD_HOST", (0, 1), None),
            LIRInstruction("CALL_BUILTIN", (1, 999, (0,)), None),
            LIRInstruction("RETURN", (1,), None),
        ),
    )
    diagnostics = verify_lir(LIRProgram((function,), 0, (), "compat"))

    assert any("invalid builtin index" in d.message for d in diagnostics)


def test_lir_verifier_rejects_wrong_builtin_arity():
    from qy.ir.lir import LIRFunction
    from qy.ir.lir import LIRInstruction
    from qy.ir.lir import LIRProgram
    from qy.ir.lir import verify_lir

    function = LIRFunction(
        name=Symbol("<main>"),
        params=(),
        register_count=2,
        instructions=(
            LIRInstruction("LOAD_HOST", (0, 1), None),
            # car 的 ABI 元数是 1
            LIRInstruction("CALL_BUILTIN", (1, BUILTIN_NAMES.index("car"), (0, 0)), None),
            LIRInstruction("RETURN", (1,), None),
        ),
    )
    diagnostics = verify_lir(LIRProgram((function,), 0, (), "compat"))

    assert any("expects 1 args" in d.message for d in diagnostics)
