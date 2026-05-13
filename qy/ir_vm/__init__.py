# coding: utf-8
"""IR Virtual Machine — reference runtime for the IR layer.

This module is the *reference* (tree-walking) runtime for QyLang's IR.  It is
kept for correctness verification and as a compatibility shim; it is NOT the
primary execution path.  The primary runtime is the register VM in
``qy/register_vm.py``, reached via the MIR → LIR → bytecode pipeline.

Use ``evaluate_ir_source`` / ``evaluate_ir_source_async`` for quick integration
tests or when you need the full evaluator semantics without going through the
bytecode compiler.
"""

from __future__ import annotations

from qy.errors import QyRuntimeError
from qy.evaluator import Environment
from qy.evaluator import run_async
from qy.evaluator import standard_environment
from qy.ir import ProgramIR
from qy.ir_vm._core import IRCallableKind
from qy.ir_vm._core import IRFunction
from qy.ir_vm._core import IRVirtualMachine

__all__ = [
    "IRCallableKind",
    "IRFunction",
    "IRVirtualMachine",
    "evaluate_ir",
    "evaluate_ir_async",
    "evaluate_ir_source",
    "evaluate_ir_source_async",
]


def evaluate_ir(program: ProgramIR, env: Environment | None = None) -> object:
    return run_async(evaluate_ir_async(program, env))


async def evaluate_ir_async(program: ProgramIR, env: Environment | None = None) -> object:
    results = await IRVirtualMachine(env).evaluate_program(program)
    return None if not results else results[-1]


def evaluate_ir_source(
    source: str,
    env: Environment | None = None,
    *,
    source_name: str | None = None,
) -> object:
    return run_async(evaluate_ir_source_async(source, env, source_name=source_name))


async def evaluate_ir_source_async(
    source: str,
    env: Environment | None = None,
    *,
    source_name: str | None = None,
) -> object:
    from qy.lowering import lower
    from qy.macroexpand import macroexpand_source_async

    runtime_env = env or standard_environment()
    expansion = await macroexpand_source_async(source, runtime_env, source_name=source_name)
    errors = tuple(item for item in expansion.diagnostics if item.severity == "error")
    if errors:
        messages = "; ".join(item.message for item in errors)
        raise QyRuntimeError(f"cannot execute macroexpanded source: {messages}")
    return await evaluate_ir_async(
        lower(expansion.forms, runtime_env),
        runtime_env,
    )
