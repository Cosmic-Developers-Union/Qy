import asyncio
from typing import cast

from qy.evaluator import standard_environment
from qy.runtime import Qy
from qy.stdlib import load_module


async def test_async_api_awaits_python_coroutines():
    qy = Qy()

    @qy.register_pure("delayed-double")
    async def delayed_double(value):
        await asyncio.sleep(0)
        return value * 2

    assert await qy.evaluate_source_async("(delayed-double 21)") == 42


async def test_parallel_evaluates_expressions_concurrently():
    qy = Qy()

    @qy.register_pure("delayed")
    async def delayed(value):
        await asyncio.sleep(0)
        return value

    assert await qy.evaluate_source_async("(parallel (delayed 1) (delayed 2))") == (1, 2)


async def test_spawn_and_await_use_asyncio_tasks():
    env = standard_environment()
    for sym, val in load_module("qy.legacy").exports.items():
        env.define(sym, val)
    qy = Qy(env=env)

    task = cast(asyncio.Task[object], await qy.evaluate_source_async("(spawn (+ 1 2))"))

    assert isinstance(task, asyncio.Task)
    assert await task == 3
    assert await qy.evaluate_source_async("(await (spawn (+ 20 22)))") == 42


async def test_cache_reuses_expression_result():
    qy = Qy()
    calls: list[int] = []

    @qy.register_pure("counted")
    def counted(value):
        calls.append(value)
        return value * 2

    assert await qy.evaluate_source_async("(cache (counted 21))") == 42
    assert await qy.evaluate_source_async("(cache (counted 21))") == 42
    assert calls == [21]
