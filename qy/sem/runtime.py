# coding: utf-8
# Copyright (C) 2025 Cosmic-Developers-Union (CDU), All rights reserved.

"""Runtime values for Qy semantic model.

This module defines runtime values that represent executable entities in the
semantic model: user-defined functions, effect definitions, and component
operators. These are semantic values shared across all backends, not
implementation-specific helpers.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from qy.errors import QyArityError
from qy.frontend.reader import Symbol

if TYPE_CHECKING:
    from qy.session.runtime_space import RuntimeSpace as Environment

__all__ = ["ComponentOperator", "EffectDefinition", "UserFunction"]


@dataclass(frozen=True, slots=True)
class EffectDefinition:
    """Effect definition in the semantic model.

    Represents a declared algebraic effect with its name and resumability.
    """

    name: Symbol
    resumable: bool = True
    doc: str = ""


@dataclass(frozen=True, slots=True)
class UserFunction:
    """User-defined function in the semantic model.

    Represents a lambda or named function with its parameters, body, and
    closure environment. This is a semantic value; the actual execution
    mechanism depends on the backend (register VM, etc.).
    """

    name: Symbol
    params: tuple[Symbol, ...]
    body: tuple[object, ...]
    closure: Environment

    async def __call__(self, *args: object) -> object:
        """Legacy execution path with tail-call optimization."""
        from qy.vm.instance.values import TailCall

        if len(args) != len(self.params):
            raise QyArityError(
                f"{self.name.name} expects {len(self.params)} arguments, got {len(args)}",
                span=self.name.span,
                metadata={
                    "expected": len(self.params),
                    "actual": len(args),
                    "function": self.name.name,
                },
            )
        current_args = args
        while True:
            local_env = self.closure.child(dict(zip(self.params, current_args, strict=True)))
            result = await _evaluate_tail_body(self.body, local_env, self)
            if not isinstance(result, TailCall) or result.function is not self:
                return result
            current_args = result.args


@dataclass(frozen=True, slots=True)
class ComponentOperator:
    """Component operator in the semantic model.

    A meta-operator that composes multiple operators. When called, it passes
    the first argument to the first operator and remaining arguments to the
    last operator, then composes results from right to left.

    Example:
        (component op1 op2 op3) with args (a, b, c) evaluates as:
        (op1 a (op2 (op3 b c)))
    """

    operators: tuple[object, ...]
    closure: Environment

    async def __call__(self, *args: object) -> object:
        """Legacy execution path for component composition."""
        from qy.core.syntax import list_to_chain
        from qy.vm.instance.machine import evaluate_form_async

        if len(args) == 0:
            raise QyArityError(
                "component operator expects at least 1 argument",
                metadata={"actual": 0},
            )

        if len(self.operators) == 1:
            # Single operator: direct call
            form = list_to_chain([self.operators[0], *args])
            return await evaluate_form_async(form, self.closure)

        # Multiple operators: first arg to first operator, rest to last
        first_arg = args[0]
        rest_args = args[1:]

        # Compose right-to-left: call last operator first
        if len(self.operators) == 2:
            # Two operators case
            op1, op2 = self.operators
            # Call op2 with remaining args
            form2 = list_to_chain([op2, *rest_args])
            result2 = await evaluate_form_async(form2, self.closure)
            # Call op1 with first arg and op2's result
            form1 = list_to_chain([op1, first_arg, result2])
            return await evaluate_form_async(form1, self.closure)
        else:
            # More than two operators: recursive composition
            # (component op1 op2 op3 ... opn) is equivalent to
            # (component op1 (component op2 op3 ... opn))
            rest_component = ComponentOperator(self.operators[1:], self.closure)
            result_rest = await rest_component(*rest_args)
            # Call first operator with first arg and composed result
            form1 = list_to_chain([self.operators[0], first_arg, result_rest])
            return await evaluate_form_async(form1, self.closure)


# -- TCO helpers for UserFunction (private to this module) --------------------


async def _evaluate_tail_body(
    body: tuple[object, ...],
    env: Environment,
    function: UserFunction,
) -> object:
    from qy.vm.instance.machine import evaluate_form_async

    if not body:
        raise QyArityError("body must contain at least one expression")
    for expression in body[:-1]:
        await evaluate_form_async(expression, env)
    return await _tail_expression(body[-1], env, function)


async def _tail_expression(
    expression: object,
    env: Environment,
    fn: UserFunction,
) -> object:
    from qy.vm.instance.machine import evaluate_form_async
    from qy.vm.instance.values import TailCall

    if _is_self_tail_call(expression, fn, env):
        assert isinstance(expression, tuple)
        return await _evaluate_values(
            tuple(expression[1:]),
            env,
            lambda arguments: TailCall(fn, arguments),
        )
    if isinstance(expression, tuple) and expression:
        operator = expression[0]
        args = tuple(expression[1:])
        if operator == Symbol("cond"):
            return await _tail_cond(args, env, fn)
        if operator == Symbol("let"):
            return await _tail_let(args, env, fn)
    return await evaluate_form_async(expression, env)


async def _tail_cond(
    args: tuple[object, ...],
    env: Environment,
    fn: UserFunction,
) -> object:
    from qy.core.syntax import nil
    from qy.errors import QyTypeError
    from qy.frontend.reader import get_span
    from qy.vm.instance.machine import evaluate_form_async

    for clause in args:
        if not isinstance(clause, tuple) or len(clause) != 2:
            raise QyTypeError(
                f"cond clause must be a pair, got {clause!r}",
                span=get_span(clause),
                metadata={"clause": clause},
            )
        condition, result = clause
        if (await evaluate_form_async(condition, env)) is not nil:
            return await _tail_expression(result, env, fn)
    return nil


async def _tail_let(
    args: tuple[object, ...],
    env: Environment,
    fn: UserFunction,
) -> object:
    from qy.core.symbol_utils import ensure_symbol
    from qy.errors import QyTypeError
    from qy.frontend.reader import get_span
    from qy.vm.instance.machine import evaluate_form_async

    if len(args) < 2:
        raise QyArityError("let expects bindings and at least one body expression")
    bindings, *let_body = args
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
            await evaluate_form_async(value_expression, local_env),
        )
    return await _evaluate_tail_body(tuple(let_body), local_env, fn)


def _is_self_tail_call(expression: object, fn: UserFunction, env: Environment) -> bool:
    from qy.errors import QyError

    if not isinstance(expression, tuple) or not expression:
        return False
    operator = expression[0]
    if not isinstance(operator, Symbol) or operator != fn.name:
        return False
    try:
        return env.resolve(operator) is fn
    except QyError:
        return False


async def _evaluate_values(
    expressions: tuple[object, ...],
    env: Environment,
    then: Callable[[tuple[object, ...]], object],
) -> object:
    from qy.errors import QyEffectSignal
    from qy.vm.instance.frame import _await_if_needed
    from qy.vm.instance.machine import evaluate_form_async

    values: list[object] = []
    for i, expr in enumerate(expressions):
        try:
            values.append(await evaluate_form_async(expr, env))
        except QyEffectSignal as e:
            _compose_values(e, expressions, i + 1, tuple(values), env, then)
            raise
    return await _await_if_needed(then(tuple(values)))


def _compose_values(
    signal: object,
    expressions: tuple[object, ...],
    index: int,
    values: tuple[object, ...],
    env: Environment,
    then: Callable[[tuple[object, ...]], object],
) -> None:
    from qy.errors import QyEffectSignal
    from qy.vm.instance.frame import QyContinuation
    from qy.vm.instance.frame import _await_if_needed
    from qy.vm.instance.machine import evaluate_form_async

    if not isinstance(signal, QyEffectSignal):
        return
    previous = signal.continuation
    if not isinstance(previous, QyContinuation):
        return

    async def resume(value: object) -> object:
        resumed = await previous.resume(value)
        new_values = [*values, resumed]
        for i in range(index, len(expressions)):
            new_values.append(await evaluate_form_async(expressions[i], env))
        return await _await_if_needed(then(tuple(new_values)))

    signal.continuation = QyContinuation(signal.effect, previous.resumable, resume)
