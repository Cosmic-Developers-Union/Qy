# coding: utf-8

from __future__ import annotations

from qy.environment import Environment
from qy.runtime_values import UserFunction

__all__ = ["evaluate_async", "evaluate_body_async", "evaluate_tail_body_async"]


async def evaluate_async(expression: object, env: Environment) -> object:
    from qy.evaluator import evaluate_async as _evaluate_async

    return await _evaluate_async(expression, env)


async def evaluate_body_async(body: tuple[object, ...], env: Environment) -> object:
    from qy.evaluator import evaluate_body_async as _evaluate_body_async

    return await _evaluate_body_async(body, env)


async def evaluate_tail_body_async(
    body: tuple[object, ...],
    env: Environment,
    function: UserFunction,
) -> object:
    from qy.evaluator import _evaluate_tail_body_async

    return await _evaluate_tail_body_async(body, env, function)
