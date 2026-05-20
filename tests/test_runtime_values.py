# coding: utf-8
"""测试 qy.runtime_values 模块。."""

from __future__ import annotations

import pytest

from qy.environment import Environment
from qy.errors import QyArityError
from qy.reader import Symbol
from qy.runtime_values import UserFunction


@pytest.mark.asyncio
async def test_user_function_call():
    """测试调用 UserFunction。."""
    env = Environment()
    func = UserFunction(
        name=Symbol("test-func"),
        params=(Symbol("x"),),
        body=(Symbol("x"),),
        closure=env,
    )

    result = await func(42)
    assert result == 42


@pytest.mark.asyncio
async def test_user_function_arity_error():
    """测试 UserFunction 参数数量错误。."""
    env = Environment()
    func = UserFunction(
        name=Symbol("test-func"),
        params=(Symbol("x"), Symbol("y")),
        body=(Symbol("x"),),
        closure=env,
    )

    with pytest.raises(QyArityError) as exc_info:
        await func(42)

    assert "expects 2 arguments, got 1" in str(exc_info.value)
    assert exc_info.value.metadata["expected"] == 2
    assert exc_info.value.metadata["actual"] == 1


@pytest.mark.asyncio
async def test_user_function_tail_call_loop():
    """测试 UserFunction 尾调用循环。."""
    from qy.eval_runtime import _TailCall

    env = Environment()

    # 创建一个简单的函数，返回 _TailCall 以触发尾调用循环
    func = UserFunction(
        name=Symbol("loop"),
        params=(Symbol("n"),),
        body=(Symbol("n"),),
        closure=env,
    )

    # 手动构造一个会触发尾调用循环的场景
    # 通过 monkey patch evaluate_tail_body_async 来返回 _TailCall
    original_eval = None
    call_count = [0]

    async def mock_eval(
        body: tuple[object, ...], env: Environment, function: UserFunction
    ) -> object:
        call_count[0] += 1
        if call_count[0] == 1:
            # 第一次调用返回 _TailCall，触发循环
            return _TailCall(function, (42,))
        else:
            # 第二次调用返回正常值，结束循环
            return 42

    import qy.eval_runtime

    original_eval = qy.eval_runtime.evaluate_tail_body_async
    qy.eval_runtime.evaluate_tail_body_async = mock_eval  # ty: ignore[invalid-assignment]

    try:
        result = await func(0)
        assert result == 42
        assert call_count[0] == 2  # 确认循环执行了两次
    finally:
        qy.eval_runtime.evaluate_tail_body_async = original_eval
