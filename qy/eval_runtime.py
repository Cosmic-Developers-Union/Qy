# coding: utf-8
# QY_DELETE_AFTER_SEMANTIC_REPLACEMENT: target=qy/std without legacy evaluator helpers
# Compatibility facade for stdlib and runtime_values.
#
# This module provides the evaluation functions needed by stdlib operators
# and UserFunction TCO, without requiring direct imports from the legacy
# evaluator module.
#
# All functions are legacy -- they will be removed once UserFunction and
# stdlib operators are migrated to use the register VM pipeline directly.

from __future__ import annotations

from collections.abc import Callable

from qy.continuation import QyContinuation
from qy.continuation import _await_if_needed
from qy.environment import Environment
from qy.errors import QyArityError
from qy.errors import QyEffectSignal
from qy.errors import QyError
from qy.errors import QyTypeError
from qy.reader import Symbol
from qy.reader import get_span
from qy.runtime_values import UserFunction
from qy.runtime_values import _TailCall
from qy.symbol_utils import ensure_symbol
from qy.values import QY_NIL

__all__ = [
    "evaluate_async",
    "evaluate_body_async",
    "evaluate_tail_body_async",
]


# -- stdlib-compatible evaluation facades (legacy, migration pending) -------


async def evaluate_async(expression: object, env: Environment) -> object:
    from qy.evaluator import evaluate_async as _evaluate_async

    return await _evaluate_async(expression, env)


async def evaluate_body_async(body: tuple[object, ...], env: Environment) -> object:
    from qy.evaluator import evaluate_body_async as _evaluate_body_async

    return await _evaluate_body_async(body, env)


# -- Tail-call optimization (legacy -- will be removed after UserFunction migration) --
#
# The TCO loop is the sole consumer of _evaluate_values / _compose_effect_continuation
# in the context of UserFunction.__call__.  Once UserFunction executes entirely
# through the register VM pipeline, this entire section can be deleted.


async def evaluate_tail_body_async(
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
    return QY_NIL


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

    return await evaluate_tail_body_async(tuple(body), local_env, function)


def _truthy(value: object) -> bool:
    return value is not QY_NIL


# -- Effect-aware value evaluation helpers (used by TCO above) --


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
