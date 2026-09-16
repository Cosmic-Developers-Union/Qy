# coding: utf-8
"""Legacy form-level evaluation path for semantic callables.

``UserFunction`` / ``ComponentOperator`` 定义在 ``qy.sem.runtime``，是语义值；
但执行它们需要 register VM 的 form 求值路径。因此实现放在 VM 实例层，避免
``qy.sem`` 反向 import ``qy.vm``。

当前：这是 migration 期路径，通过 ``evaluate_form_async`` 逐 form 编译执行；
``lambda`` / ``defun`` 的正式运行时表示应逐步收敛到 bytecode function。
"""

from __future__ import annotations

from collections.abc import Callable

from qy.core.syntax import Symbol
from qy.errors import QyArityError
from qy.sem.runtime import ComponentOperator
from qy.sem.runtime import UserFunction
from qy.session.runtime_space import RuntimeSpace as Environment

__all__ = ["call_component_operator", "call_user_function"]


async def call_user_function(function: UserFunction, args: tuple[object, ...]) -> object:
    """执行 ``UserFunction``（legacy 路径，含尾调用优化）。."""
    from qy.vm.instance.values import TailCall

    if len(args) != len(function.params):
        raise QyArityError(
            f"{function.name.name} expects {len(function.params)} arguments, got {len(args)}",
            span=function.name.span,
            metadata={
                "expected": len(function.params),
                "actual": len(args),
                "function": function.name.name,
            },
        )
    current_args = args
    while True:
        local_env = function.closure.child(dict(zip(function.params, current_args, strict=True)))
        result = await _evaluate_tail_body(function.body, local_env, function)
        if not isinstance(result, TailCall) or result.function is not function:
            return result
        current_args = result.args


async def call_component_operator(operator: ComponentOperator, args: tuple[object, ...]) -> object:
    """执行 ``ComponentOperator``（legacy 路径）。."""
    from qy.core.syntax import list_to_chain
    from qy.vm.instance.machine import evaluate_form_async

    if len(args) == 0:
        raise QyArityError(
            "component operator expects at least 1 argument",
            metadata={"actual": 0},
        )

    if len(operator.operators) == 1:
        form = list_to_chain([operator.operators[0], *args])
        return await evaluate_form_async(form, operator.closure)

    first_arg = args[0]
    rest_args = args[1:]

    if len(operator.operators) == 2:
        op1, op2 = operator.operators
        form2 = list_to_chain([op2, *rest_args])
        result2 = await evaluate_form_async(form2, operator.closure)
        form1 = list_to_chain([op1, first_arg, result2])
        return await evaluate_form_async(form1, operator.closure)

    rest_component = ComponentOperator(operator.operators[1:], operator.closure)
    result_rest = await call_component_operator(rest_component, rest_args)
    form1 = list_to_chain([operator.operators[0], first_arg, result_rest])
    return await evaluate_form_async(form1, operator.closure)


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
    from qy.core.syntax import get_span
    from qy.core.syntax import nil
    from qy.errors import QyTypeError
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
    from qy.core.syntax import get_span
    from qy.errors import QyTypeError
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
