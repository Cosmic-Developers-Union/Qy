# coding: utf-8
"""测试 qy.sem.runtime 模块。."""

from __future__ import annotations

import pytest

from qy.environment import Environment
from qy.errors import QyArityError
from qy.frontend.reader import Symbol
from qy.sem.runtime import ComponentOperator
from qy.sem.runtime import EffectDefinition
from qy.sem.runtime import UserFunction


def test_effect_definition_creation():
    """测试创建 EffectDefinition。."""
    effect = EffectDefinition(
        name=Symbol("test-effect"),
        resumable=True,
        doc="Test effect",
    )
    assert effect.name.name == "test-effect"
    assert effect.resumable is True
    assert effect.doc == "Test effect"


def test_effect_definition_defaults():
    """测试 EffectDefinition 默认值。."""
    effect = EffectDefinition(name=Symbol("test-effect"))
    assert effect.resumable is True
    assert effect.doc == ""


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
    from qy.vm.instance.values import TailCall

    env = Environment()

    # 创建一个简单的函数，返回 TailCall 以触发尾调用循环
    func = UserFunction(
        name=Symbol("loop"),
        params=(Symbol("n"),),
        body=(Symbol("n"),),
        closure=env,
    )

    # 手动构造一个会触发尾调用循环的场景
    # 通过 monkey patch _evaluate_tail_body 来返回 TailCall
    original_eval = None
    call_count = [0]

    async def mock_eval(
        body: tuple[object, ...], env: Environment, function: UserFunction
    ) -> object:
        call_count[0] += 1
        if call_count[0] == 1:
            # 第一次调用返回 TailCall，触发循环
            return TailCall(function, (42,))
        else:
            # 第二次调用返回正常值，结束循环
            return 42

    import qy.sem.runtime

    original_eval = qy.sem.runtime._evaluate_tail_body
    qy.sem.runtime._evaluate_tail_body = mock_eval  # ty: ignore[invalid-assignment]

    try:
        result = await func(0)
        assert result == 42
        assert call_count[0] == 2  # 确认循环执行了两次
    finally:
        qy.sem.runtime._evaluate_tail_body = original_eval


@pytest.mark.asyncio
async def test_component_operator_single():
    """测试单个算子的 ComponentOperator。."""
    from qy.core.syntax import list_to_chain

    env = Environment()

    # 创建一个简单的算子（使用 lambda）
    add_one = UserFunction(
        name=Symbol("add-one"),
        params=(Symbol("x"),),
        body=(list_to_chain([Symbol("+"), Symbol("x"), 1]),),
        closure=env,
    )

    comp = ComponentOperator(operators=(add_one,), closure=env)

    # 单个算子应该直接调用
    # 注意：这需要 evaluate_async 能够处理，这里只测试结构
    assert len(comp.operators) == 1
    assert comp.operators[0] is add_one


@pytest.mark.asyncio
async def test_component_operator_arity_error():
    """测试 ComponentOperator 参数数量错误。."""
    env = Environment()
    comp = ComponentOperator(operators=(Symbol("op1"),), closure=env)

    with pytest.raises(QyArityError) as exc_info:
        await comp()

    assert "expects at least 1 argument" in str(exc_info.value)
    assert exc_info.value.metadata["actual"] == 0


def test_user_function_immutable():
    """测试 UserFunction 是不可变的。."""
    env = Environment()
    func = UserFunction(
        name=Symbol("test-func"),
        params=(Symbol("x"),),
        body=(Symbol("x"),),
        closure=env,
    )

    with pytest.raises(AttributeError):
        func.name = Symbol("new-name")  # ty: ignore[misc]


def test_effect_definition_immutable():
    """测试 EffectDefinition 是不可变的。."""
    effect = EffectDefinition(name=Symbol("test-effect"))

    with pytest.raises(AttributeError):
        effect.resumable = False  # ty: ignore[misc]


def test_component_operator_immutable():
    """测试 ComponentOperator 是不可变的。."""
    env = Environment()
    comp = ComponentOperator(operators=(Symbol("op1"),), closure=env)

    with pytest.raises(AttributeError):
        comp.operators = (Symbol("op2"),)  # ty: ignore[misc]
