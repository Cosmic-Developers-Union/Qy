# coding: utf-8
# QY_DELETE_AFTER_SEMANTIC_REPLACEMENT: target=register VM + compile-time macro execution
# Legacy evaluator module - backward compatibility layer.
#
# This module provides backward compatibility for code using the old evaluator API.
# New code should use:
#   - qy.runtime.Qy / qy.runtime.AsyncQy for evaluation
#   - qy.vm.instance.machine for low-level VM operations
#
# This module will be removed once all external code has migrated.

from __future__ import annotations

from pathlib import Path
from typing import cast

# Re-export sub-module symbols for backward compatibility.
from qy.core.operators import ArgumentEvaluator  # noqa: F401
from qy.core.operators import ControlOperator
from qy.core.operators import EffectOperator
from qy.core.operators import EvaluationOperator
from qy.core.operators import MetaOperator
from qy.core.operators import PureOperator
from qy.core.operators import ScopeOperator
from qy.core.operators import SyntaxOperator
from qy.core.symbol_utils import ensure_symbol
from qy.core.syntax import Chain as QyChain
from qy.core.syntax import Chain as QyCons
from qy.core.syntax import nil as QY_EMPTY_CHAIN
from qy.core.syntax import nil as QY_EMPTY_LIST
from qy.core.syntax import nil as QY_NIL
from qy.environment import Environment
from qy.environment import standard_environment
from qy.errors import EvaluationError
from qy.errors import QyResolveError
from qy.errors import QyRuntimeError
from qy.errors import SourceSpan
from qy.errors import TraceFrame
from qy.frontend.reader import read
from qy.macro import MacroDefinition
from qy.sem.core import T as QY_T
from qy.sem.runtime import EffectDefinition
from qy.sem.runtime import UserFunction
from qy.vm.instance.frame import QyContinuation
from qy.vm.instance.values import HostObjectRef

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


# -- Public evaluation API (legacy, routes to new implementation) -----------


def evaluate(expression: object, env: Environment | None = None) -> object:
    """Evaluate a single expression.

    DEPRECATED: Use qy.runtime.Qy().evaluate() instead.
    """
    from qy.async_utils import run_coro

    return run_coro(evaluate_async(expression, env))


async def evaluate_async(expression: object, env: Environment | None = None) -> object:
    """Evaluate a single expression asynchronously.

    DEPRECATED: Use qy.runtime.AsyncQy().evaluate() instead.
    """
    from qy.vm.instance.machine import evaluate_form_async

    runtime_env = env or standard_environment()
    return await evaluate_form_async(expression, runtime_env)


def evaluate_source(
    source: str, env: Environment | None = None, *, source_name: str | None = None
) -> object:
    """Evaluate source code and return the last result.

    DEPRECATED: Use qy.runtime.Qy().evaluate_source() instead.
    """
    from qy.async_utils import run_coro

    return run_coro(evaluate_source_async(source, env, source_name=source_name))


async def evaluate_source_async(
    source: str, env: Environment | None = None, *, source_name: str | None = None
) -> object:
    """Evaluate source code asynchronously and return the last result.

    DEPRECATED: Use qy.runtime.AsyncQy().evaluate_source() instead.
    """
    from qy.backend.vm.compiler import compile_bytecode
    from qy.macro import macroexpand_async
    from qy.passes.lower_hir import lower

    runtime_env = env or standard_environment()
    expansion = await macroexpand_async(read(source, source_name=source_name), runtime_env)
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

    from qy.vm.instance.machine import evaluate_bytecode_async

    bytecode = compile_bytecode(program)
    bytecode_errors = tuple(item for item in bytecode.diagnostics if item.severity == "error")
    if bytecode_errors:
        messages = "; ".join(item.message for item in bytecode_errors)
        first = bytecode_errors[0]
        raise QyRuntimeError(
            f"cannot evaluate bytecode program with diagnostics: {messages}",
            span=SourceSpan(start_line=first.line, start_column=first.column),
        )

    results = await evaluate_bytecode_async(bytecode, runtime_env)
    return results


def evaluate_program(
    source: str, env: Environment | None = None, *, source_name: str | None = None
) -> list[object]:
    """Evaluate source code and return all results.

    DEPRECATED: Use qy.runtime.Qy().evaluate_program() instead.
    """
    from qy.async_utils import run_coro

    return cast(
        list[object],
        run_coro(evaluate_program_async(source, env, source_name=source_name)),
    )


async def evaluate_program_async(
    source: str, env: Environment | None = None, *, source_name: str | None = None
) -> list[object]:
    """Evaluate source code asynchronously and return all results.

    DEPRECATED: Use qy.runtime.AsyncQy().evaluate_program() instead.
    """
    from qy.backend.vm.compiler import compile_bytecode
    from qy.macro import macroexpand_async
    from qy.passes.lower_hir import lower
    from qy.vm.instance.machine import RegisterVirtualMachine

    runtime_env = env or standard_environment()
    expansion = await macroexpand_async(read(source, source_name=source_name), runtime_env)
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


def evaluate_file(path: str | Path, env: Environment | None = None) -> object:
    """Evaluate a file and return the last result.

    DEPRECATED: Use qy.runtime.Qy().evaluate_file() instead.
    """
    from qy.async_utils import run_coro

    return run_coro(evaluate_file_async(path, env))


async def evaluate_file_async(path: str | Path, env: Environment | None = None) -> object:
    """Evaluate a file asynchronously and return the last result.

    DEPRECATED: Use qy.runtime.AsyncQy().evaluate_file() instead.
    """
    path = Path(path)
    source = path.read_text(encoding="utf-8")
    results = await evaluate_program_async(source, env, source_name=str(path))
    if not results:
        return None
    return results[-1]


# -- Body evaluation with effect support (used by stdlib) -------------------


def evaluate_body(body: tuple[object, ...], env: Environment) -> object:
    """Evaluate a sequence of expressions, returning the last result.

    Used internally by stdlib operators that need to evaluate bodies with
    effect support.
    """
    from qy.async_utils import run_coro
    from qy.vm.instance.machine import evaluate_form_body_async

    return run_coro(evaluate_form_body_async(body, env))


async def evaluate_body_async(body: tuple[object, ...], env: Environment) -> object:
    """Evaluate a sequence of expressions asynchronously, returning the last result.

    Used internally by stdlib operators that need to evaluate bodies with
    effect support.
    """
    from qy.vm.instance.machine import evaluate_form_body_async

    return await evaluate_form_body_async(body, env)
