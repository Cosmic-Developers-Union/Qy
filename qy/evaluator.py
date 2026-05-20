# coding: utf-8
# QY_DELETE_AFTER_SEMANTIC_REPLACEMENT: target=register VM + compile-time macro execution
# Legacy evaluator module.
#
# This module is being phased out in favor of the register VM pipeline.
# The remaining functions fall into two categories:
#
#   1. Public evaluation API (evaluate, evaluate_source, evaluate_program,
#      evaluate_file, evaluate_body) -- used by tests.  These route through
#      the full pipeline (macroexpand -> lower -> compile -> VM).
#
#   2. Internal helpers for body evaluation with effect support
#      (_evaluate_body_from, _continue_body_after_resume, _compose_effect_continuation).
#
# DO NOT add new functionality here.  New code should use the register VM
# pipeline directly or go through eval_runtime.py for compatibility.

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import cast

import asyncio
from qy.continuation import QyContinuation
from qy.continuation import _await_if_needed
from qy.environment import Environment
from qy.environment import standard_environment
from qy.errors import EvaluationError
from qy.errors import QyArityError
from qy.errors import QyEffectSignal
from qy.errors import QyResolveError
from qy.errors import QyRuntimeError
from qy.errors import SourceSpan
from qy.errors import TraceFrame
from qy.macro import MacroDefinition

# Re-export sub-module symbols for backward compatibility.
from qy.operators import ArgumentEvaluator  # noqa: F401
from qy.operators import ControlOperator
from qy.operators import EffectOperator
from qy.operators import EvaluationOperator
from qy.operators import MetaOperator
from qy.operators import PureOperator
from qy.operators import ScopeOperator
from qy.operators import SyntaxOperator
from qy.reader import Form
from qy.reader import Symbol
from qy.reader import read
from qy.runtime_values import EffectDefinition
from qy.runtime_values import HostObjectRef
from qy.runtime_values import UserFunction
from qy.symbol_utils import ensure_symbol
from qy.values import QY_EMPTY_CHAIN
from qy.values import QY_EMPTY_LIST
from qy.values import QY_NIL
from qy.values import QY_T
from qy.values import QyChain
from qy.values import QyCons

__all__ = [
    "QY_EMPTY_CHAIN",
    "QY_EMPTY_LIST",
    "QY_NIL",
    "QY_T",
    "ControlOperator",
    "EffectDefinition",
    "EffectOperator",
    "Environment",
    "EvaluationError",
    "EvaluationOperator",
    "HostObjectRef",
    "MacroDefinition",
    "MetaOperator",
    "PureOperator",
    "QyChain",
    "QyCons",
    "QyContinuation",
    "ScopeOperator",
    "SyntaxOperator",
    "UserFunction",
    "ensure_symbol",
    "evaluate",
    "evaluate_async",
    "evaluate_body",
    "evaluate_body_async",
    "evaluate_file",
    "evaluate_file_async",
    "evaluate_program",
    "evaluate_program_async",
    "evaluate_source",
    "evaluate_source_async",
    "standard_environment",
]


# -- Public evaluation API (legacy, used by tests) --------------------------


def _run_coro(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(1) as pool:
        return pool.submit(asyncio.run, coro).result()


def evaluate(expression: object, env: Environment | None = None) -> object:
    return _run_coro(evaluate_async(expression, env))


async def evaluate_async(expression: object, env: Environment | None = None) -> object:
    runtime_env = env or standard_environment()
    if isinstance(expression, Symbol):
        return runtime_env.resolve(expression)
    results = await _evaluate_ir_forms_async([cast(Form, expression)], runtime_env)
    return None if not results else results[-1]


def evaluate_source(
    source: str, env: Environment | None = None, *, source_name: str | None = None
) -> object:
    return _run_coro(evaluate_source_async(source, env, source_name=source_name))


async def evaluate_source_async(
    source: str, env: Environment | None = None, *, source_name: str | None = None
) -> object:
    results = await _evaluate_ir_forms_async(read(source, source_name=source_name), env)
    return None if not results else results[-1]


def evaluate_program(
    source: str, env: Environment | None = None, *, source_name: str | None = None
) -> list[object]:
    return cast(
        list[object],
        _run_coro(evaluate_program_async(source, env, source_name=source_name)),
    )


async def evaluate_program_async(
    source: str, env: Environment | None = None, *, source_name: str | None = None
) -> list[object]:
    return await _evaluate_ir_forms_async(read(source, source_name=source_name), env)


def evaluate_file(path: str | Path, env: Environment | None = None) -> object:
    return _run_coro(evaluate_file_async(path, env))


async def evaluate_file_async(path: str | Path, env: Environment | None = None) -> object:
    path = Path(path)
    source = path.read_text(encoding="utf-8")
    results = await evaluate_program_async(source, env, source_name=str(path))
    if not results:
        return None
    return results[-1]


# -- Pipeline execution (macroexpand -> lower -> compile -> VM) -------------


async def _evaluate_ir_forms_async(
    forms: list[Form],
    env: Environment | None = None,
) -> list[object]:
    runtime_env = env or standard_environment()

    from qy.bytecode_compiler import compile_bytecode
    from qy.macroexpand import macroexpand_async
    from qy.passes.lower_hir import lower
    from qy.register_vm import RegisterVirtualMachine

    expansion = await macroexpand_async(forms, runtime_env)
    program = lower(expansion.forms, runtime_env)
    diagnostics = (*expansion.diagnostics, *program.diagnostics)
    errors = tuple(item for item in diagnostics if item.severity == "error")
    if errors:
        if len(errors) == 1 and errors[0].message.startswith("unresolved symbol "):
            symbol = errors[0].message.removeprefix("unresolved symbol ").strip("'")
            span = SourceSpan(start_line=errors[0].line, start_column=errors[0].column)
            raise QyResolveError(
                errors[0].message,
                span=span,
                frames=(TraceFrame("call", None, span),),
                metadata={"symbol": symbol},
            )
        messages = "; ".join(item.message for item in errors)
        first = errors[0]
        raise QyRuntimeError(
            f"cannot evaluate program with diagnostics: {messages}",
            span=SourceSpan(start_line=first.line, start_column=first.column),
        )
    bytecode = compile_bytecode(program)
    bytecode_errors = tuple(item for item in bytecode.diagnostics if item.severity == "error")
    if bytecode_errors:
        messages = "; ".join(item.message for item in bytecode_errors)
        first = bytecode_errors[0]
        raise QyRuntimeError(
            f"cannot evaluate bytecode program with diagnostics: {messages}",
            span=SourceSpan(start_line=first.line, start_column=first.column),
        )
    return await RegisterVirtualMachine(bytecode, runtime_env).evaluate_program()


# -- Body evaluation with effect support (legacy, used by stdlib) -----------


def evaluate_body(body: tuple[object, ...], env: Environment) -> object:
    return _run_coro(evaluate_body_async(body, env))


async def evaluate_body_async(body: tuple[object, ...], env: Environment) -> object:
    if not body:
        raise QyArityError("body must contain at least one expression")
    return await _evaluate_body_from(body, 0, env)


async def _evaluate_body_from(
    body: tuple[object, ...],
    index: int,
    env: Environment,
) -> object:
    result = None
    for current in range(index, len(body)):
        try:
            result = await evaluate_async(body[current], env)
        except QyEffectSignal as e:
            _compose_effect_continuation(
                e,
                lambda resumed, next_index=current + 1: _continue_body_after_resume(
                    body,
                    next_index,
                    resumed,
                    env,
                ),
            )
            raise
    return result


async def _continue_body_after_resume(
    body: tuple[object, ...],
    index: int,
    resumed: object,
    env: Environment,
) -> object:
    if index >= len(body):
        return resumed
    return await _evaluate_body_from(body, index, env)


def _compose_effect_continuation(
    signal: QyEffectSignal,
    then: Callable[[object], object],
) -> None:
    previous = signal.continuation
    if not isinstance(previous, QyContinuation):
        return

    async def resume(value: object) -> object:
        previous_result = await previous.resume(value)
        return await _await_if_needed(then(previous_result))

    signal.continuation = QyContinuation(signal.effect, previous.resumable, resume)
