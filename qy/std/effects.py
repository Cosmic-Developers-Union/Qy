# coding: utf-8
# QY_DELETE_AFTER_SEMANTIC_REPLACEMENT: target=qy/std/*

from __future__ import annotations

import asyncio
import inspect

from qy.environment import Environment
from qy.errors import QyAggregateError
from qy.errors import QyArityError
from qy.errors import QyCancelledError
from qy.errors import QyError
from qy.errors import QyRuntimeError
from qy.errors import QyTypeError
from qy.eval_runtime import evaluate_async
from qy.operators import ControlOperator
from qy.operators import EffectOperator
from qy.operators import ScopeOperator
from qy.reader import Symbol
from qy.reader import get_span
from qy.runtime_values import EffectDefinition
from qy.symbol_utils import ensure_symbol


def _cache_key(expression: object) -> object:
    try:
        hash(expression)
    except TypeError:
        return repr(expression)
    return expression


async def _await_cached_value(value: object) -> object:
    if inspect.isawaitable(value):
        return await value
    return value


def _exception_to_qy_error(error: BaseException) -> QyError:
    if isinstance(error, QyError):
        return error
    if isinstance(error, asyncio.CancelledError):
        return QyCancelledError("task cancelled", cause=error)
    return QyRuntimeError(
        str(error),
        cause=error,
        metadata={"python_exception": type(error).__name__},
    )


def _defeffect(args: tuple[object, ...], env: Environment) -> object:
    if not args:
        raise QyArityError("defeffect expects an effect name")

    name, *options = args
    name = ensure_symbol(name, "defeffect name")
    resumable = _parse_defeffect_resumable(tuple(options))
    effect = EffectDefinition(name, resumable=resumable)
    return env.define_once(name, effect)


def _parse_defeffect_resumable(options: tuple[object, ...]) -> bool:
    if not options:
        return True
    if len(options) != 2 or options[0] != Symbol(":resumable"):
        raise QyTypeError(
            "defeffect options must be empty or :resumable true|false",
            span=get_span(options[0]) if options else None,
        )
    value = options[1]
    if value == Symbol("true"):
        return True
    if value == Symbol("false"):
        return False
    raise QyTypeError(
        f"defeffect :resumable expects true or false, got {value!r}",
        span=get_span(value),
    )


def _special_effect_form(args: tuple[object, ...], env: Environment) -> object:
    del args, env
    raise QyRuntimeError("effect special forms are handled by the evaluator")


async def _parallel(args: tuple[object, ...], env: Environment) -> tuple[object, ...]:
    tasks = [asyncio.create_task(evaluate_async(arg, env)) for arg in args]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    errors = tuple(
        _exception_to_qy_error(result) for result in results if isinstance(result, BaseException)
    )
    if errors:
        raise QyAggregateError(
            f"parallel failed with {len(errors)} error(s)",
            errors=errors,
        )
    return tuple(results)


async def _cache(args: tuple[object, ...], env: Environment) -> object:
    if len(args) != 1:
        raise QyArityError(
            f"cache expects exactly one argument, got {len(args)}",
            metadata={"expected": 1, "actual": len(args)},
        )

    key = _cache_key(args[0])
    try:
        return await _await_cached_value(env.cache_lookup(key))
    except KeyError:
        pass

    task = asyncio.create_task(evaluate_async(args[0], env))
    env.cache_define(key, task)
    try:
        result = await task
    except Exception:
        env.cache_discard(key)
        raise
    env.cache_define(key, result)
    return result


def _spawn(args: tuple[object, ...], env: Environment) -> asyncio.Task[object]:
    if len(args) != 1:
        raise QyArityError(
            f"spawn expects exactly one argument, got {len(args)}",
            metadata={"expected": 1, "actual": len(args)},
        )
    return asyncio.create_task(evaluate_async(args[0], env))


async def _await(args: tuple[object, ...], env: Environment) -> object:
    if not args:
        raise QyArityError("await expects at least one argument")

    values: list[object] = []
    for arg in args:
        value = await evaluate_async(arg, env)
        values.append(await _await_cached_value(value))

    if len(values) == 1:
        return values[0]
    return tuple(values)


def operators() -> dict[Symbol, object]:
    return {
        Symbol("assert"): EffectOperator(
            "assert", _special_effect_form, "断言 debug 条件；失败时执行 assert-failed。"
        ),
        Symbol("cache"): EffectOperator("cache", _cache, "缓存一个表达式的求值结果。"),
        Symbol("defeffect"): ScopeOperator(
            "defeffect", _defeffect, "声明 effect，供 perform/handle 和分析器使用。"
        ),
        Symbol("handle"): ControlOperator(
            "handle", _special_effect_form, "处理表达式产生的 effect。"
        ),
        Symbol("parallel"): EffectOperator(
            "parallel", _parallel, "用 asyncio task 并发表达式求值。"
        ),
        Symbol("perform"): EffectOperator("perform", _special_effect_form, "执行 effect。"),
        Symbol("resume"): EffectOperator(
            "resume", _special_effect_form, "恢复捕获的 effect continuation。"
        ),
        Symbol("assert-failed"): EffectDefinition(
            Symbol("assert-failed"),
            resumable=False,
            doc="assert 失败产生的不可恢复 effect。",
        ),
        Symbol("python-error"): EffectDefinition(
            Symbol("python-error"),
            resumable=False,
            doc="py 宿主边界传播的 Python 异常 effect。",
        ),
    }


def legacy_operators() -> dict[Symbol, object]:
    return {
        Symbol("await"): EffectOperator("await", _await, "等待一个或多个异步值。"),
        Symbol("spawn"): EffectOperator("spawn", _spawn, "创建 asyncio task。"),
    }
