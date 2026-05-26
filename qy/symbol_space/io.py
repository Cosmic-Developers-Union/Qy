# coding: utf-8

from __future__ import annotations

from qy.core.operators import EffectOperator
from qy.display import format_value
from qy.errors import EvaluationError
from qy.frontend.reader import Symbol
from qy.import_.module import StandardModule
from qy.session.runtime_space import RuntimeSpace as Environment
from qy.vm.instance.machine import evaluate_form_async as evaluate_async


def module() -> StandardModule:
    print_operator = EffectOperator("print", _print, "打印求值后的值，并返回最后一个打印值。")
    return StandardModule(
        "qy.io",
        {
            Symbol("print"): print_operator,
            Symbol("echo"): EffectOperator(
                "echo", _print, "print 的别名；打印值并返回最后一个值。"
            ),
        },
    )


async def _print(args: tuple[object, ...], env: Environment) -> object:
    values = tuple([await _evaluate_print_arg(arg, env) for arg in args])
    print(" ".join(format_value(value) for value in values))
    if not values:
        return None
    return values[-1]


async def _evaluate_print_arg(expression: object, env: Environment) -> object:
    try:
        return await evaluate_async(expression, env)
    except EvaluationError:
        if isinstance(expression, Symbol):
            return expression
        raise
