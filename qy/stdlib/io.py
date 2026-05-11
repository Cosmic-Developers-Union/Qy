# coding: utf-8

from __future__ import annotations

from typing import cast

from qy.evaluator import EffectOperator
from qy.evaluator import Environment
from qy.evaluator import EvaluationError
from qy.evaluator import evaluate_async
from qy.reader import Symbol
from qy.reader import TupleForm
from qy.reader import write_tuple
from qy.stdlib.module import StandardModule


def module() -> StandardModule:
    print_operator = EffectOperator(
        "print", _print, "Print evaluated values and return the last printed value."
    )
    return StandardModule(
        "qy.io",
        {
            Symbol("print"): print_operator,
            Symbol("echo"): EffectOperator(
                "echo", _print, "Alias for print; prints values and returns the last value."
            ),
        },
    )


async def _print(args: tuple[object, ...], env: Environment) -> object:
    values = tuple([await _evaluate_print_arg(arg, env) for arg in args])
    print(" ".join(_format_value(value) for value in values))
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


def _format_value(value: object) -> str:
    if isinstance(value, Symbol | tuple | int | float | bool) or value is None:
        try:
            return write_tuple(cast(TupleForm, value))
        except TypeError:
            pass
    return repr(value)
