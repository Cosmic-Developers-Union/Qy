import asyncio
from typing import cast

from qy.import_.registry import load_module
from qy.runtime import AsyncQy
from qy.session.runtime_space import create_standard_runtime_space as standard_environment


async def test_async_api_awaits_python_coroutines():
    qy = AsyncQy()

    @qy.register_pure("delayed-double")
    async def delayed_double(value):
        await asyncio.sleep(0)
        return value * 2

    assert await qy.evaluate_source("(delayed-double 21)") == 42


async def test_parallel_evaluates_expressions_concurrently():
    qy = AsyncQy()

    @qy.register_pure("delayed")
    async def delayed(value):
        await asyncio.sleep(0)
        return value

    assert await qy.evaluate_source("(parallel (delayed 1) (delayed 2))") == (1, 2)


async def test_spawn_and_await_use_asyncio_tasks():
    env = standard_environment()
    for sym, val in load_module("qy.legacy").exports.items():
        env.define(sym, val)
    qy = AsyncQy(env=env)

    task = cast(asyncio.Task[object], await qy.evaluate_source("(spawn (+ 1 2))"))

    assert isinstance(task, asyncio.Task)
    assert await task == 3
    assert await qy.evaluate_source("(await (spawn (+ 20 22)))") == 42


async def test_cache_reuses_expression_result():
    qy = AsyncQy()
    calls: list[int] = []

    @qy.register_pure("counted")
    def counted(value):
        calls.append(value)
        return value * 2

    assert await qy.evaluate_source("(cache (counted 21))") == 42
    assert await qy.evaluate_source("(cache (counted 21))") == 42
    assert calls == [21]
