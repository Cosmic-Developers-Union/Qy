# coding: utf-8

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import cast

from qy.async_runtime import run_async
from qy.continuation import QyContinuation
from qy.continuation import _await_if_needed
from qy.environment import Environment
from qy.environment import standard_environment
from qy.errors import EvaluationError
from qy.errors import QyArityError
from qy.errors import QyEffectSignal
from qy.errors import QyError
from qy.errors import QyResolveError
from qy.errors import QyRuntimeError
from qy.errors import QyTypeError
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
from qy.reader import get_span
from qy.reader import read
from qy.runtime_values import EffectDefinition
from qy.runtime_values import HostObjectRef
from qy.runtime_values import UserFunction
from qy.runtime_values import _TailCall
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
    "run_async",
    "standard_environment",
]


def evaluate(expression: object, env: Environment | None = None) -> object:
    return run_async(evaluate_async(expression, env))


async def evaluate_async(expression: object, env: Environment | None = None) -> object:
    runtime_env = env or standard_environment()
    if isinstance(expression, Symbol):
        return runtime_env.resolve(expression)
    results = await _evaluate_ir_forms_async([cast(Form, expression)], runtime_env)
    return None if not results else results[-1]


def evaluate_source(
    source: str, env: Environment | None = None, *, source_name: str | None = None
) -> object:
    return run_async(evaluate_source_async(source, env, source_name=source_name))


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
        run_async(evaluate_program_async(source, env, source_name=source_name)),
    )


async def evaluate_program_async(
    source: str, env: Environment | None = None, *, source_name: str | None = None
) -> list[object]:
    return await _evaluate_ir_forms_async(read(source, source_name=source_name), env)


def evaluate_file(path: str | Path, env: Environment | None = None) -> object:
    return run_async(evaluate_file_async(path, env))


async def evaluate_file_async(path: str | Path, env: Environment | None = None) -> object:
    path = Path(path)
    source = path.read_text(encoding="utf-8")
    results = await evaluate_program_async(source, env, source_name=str(path))
    if not results:
        return None
    return results[-1]


async def _evaluate_ir_forms_async(
    forms: list[Form],
    env: Environment | None = None,
) -> list[object]:
    runtime_env = env or standard_environment()

    from qy.bytecode_compiler import compile_bytecode
    from qy.lowering import lower
    from qy.macroexpand import macroexpand_async
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


def evaluate_body(body: tuple[object, ...], env: Environment) -> object:
    return run_async(evaluate_body_async(body, env))


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


from qy.symbol_utils import ensure_symbol  # noqa: E402


async def _evaluate_values(
    expressions: tuple[object, ...],
    env: Environment,
    then: Callable[[tuple[object, ...]], object],
) -> object:
    return await _evaluate_values_from(expressions, 0, (), env, then)


async def _evaluate_values_from(
    expressions: tuple[object, ...],
    index: int,
    values: tuple[object, ...],
    env: Environment,
    then: Callable[[tuple[object, ...]], object],
) -> object:
    if index >= len(expressions):
        return await _await_if_needed(then(values))
    try:
        value = await evaluate_async(expressions[index], env)
    except QyEffectSignal as e:
        _compose_effect_continuation(
            e,
            lambda resumed: _evaluate_values_from(
                expressions,
                index + 1,
                (*values, resumed),
                env,
                then,
            ),
        )
        raise
    return await _evaluate_values_from(expressions, index + 1, (*values, value), env, then)


async def _evaluate_tail_body_async(
    body: tuple[object, ...],
    env: Environment,
    function: UserFunction,
) -> object:
    if not body:
        raise QyArityError("body must contain at least one expression")
    for expression in body[:-1]:
        await evaluate_async(expression, env)
    return await _evaluate_tail_expression_async(body[-1], env, function)


async def _evaluate_tail_expression_async(
    expression: object,
    env: Environment,
    function: UserFunction,
) -> object:
    if _is_self_tail_call(expression, function, env):
        assert isinstance(expression, tuple)
        return await _evaluate_values(
            tuple(expression[1:]),
            env,
            lambda arguments: _TailCall(function, arguments),
        )
    if isinstance(expression, tuple) and expression:
        operator = expression[0]
        args = tuple(expression[1:])
        if operator == Symbol("cond"):
            return await _evaluate_tail_cond_async(args, env, function)
        if operator == Symbol("let"):
            return await _evaluate_tail_let_async(args, env, function)
    return await evaluate_async(expression, env)


def _is_self_tail_call(expression: object, function: UserFunction, env: Environment) -> bool:
    if not isinstance(expression, tuple) or not expression:
        return False
    operator = expression[0]
    if not isinstance(operator, Symbol) or operator != function.name:
        return False
    try:
        return env.resolve(operator) is function
    except QyError:
        return False


async def _evaluate_tail_cond_async(
    args: tuple[object, ...],
    env: Environment,
    function: UserFunction,
) -> object:
    for clause in args:
        if not isinstance(clause, tuple) or len(clause) != 2:
            raise QyTypeError(
                f"cond clause must be a pair, got {clause!r}",
                span=get_span(clause),
                metadata={"clause": clause},
            )
        condition, result = clause
        if _truthy(await evaluate_async(condition, env)):
            return await _evaluate_tail_expression_async(result, env, function)
    return None


async def _evaluate_tail_let_async(
    args: tuple[object, ...],
    env: Environment,
    function: UserFunction,
) -> object:
    if len(args) < 2:
        raise QyArityError("let expects bindings and at least one body expression")

    bindings, *body = args
    if not isinstance(bindings, tuple):
        raise QyTypeError(
            f"let bindings must be a list, got {bindings!r}",
            span=get_span(bindings),
        )

    local_env = env.child()
    for binding in bindings:
        if not isinstance(binding, tuple) or len(binding) != 2:
            raise QyTypeError(
                f"let binding must be a pair, got {binding!r}",
                span=get_span(binding),
            )
        name, value_expression = binding
        local_env.define(
            ensure_symbol(name, "let binding name"),
            await evaluate_async(value_expression, local_env),
        )

    return await _evaluate_tail_body_async(tuple(body), local_env, function)


def _truthy(value: object) -> bool:
    return value not in (False, None, ())


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
