# coding: utf-8
"""测试 evaluate_form_async / evaluate_form_body_async 功能。.

这些测试验证 VM 管线中的表达式求值正确性。
"""

from __future__ import annotations

import pytest

from qy.core.syntax import Symbol
from qy.core.syntax import list_to_chain
from qy.errors import QyArityError
from qy.frontend.reader import read
from qy.session.runtime_space import create_standard_runtime_space as standard_environment
from qy.vm.instance.machine import evaluate_form_async as evaluate_async
from qy.vm.instance.machine import evaluate_form_body_async as evaluate_body_async


def L(*items: object) -> object:
    """构造一个 Qy call form（chain）。."""
    return list_to_chain(list(items))


@pytest.mark.asyncio
async def test_evaluate_async_symbol_resolution():
    """测试 evaluate_async 解析符号。."""
    env = standard_environment()
    env.define(Symbol("x"), 42)

    result = await evaluate_async(Symbol("x"), env)
    assert result == 42


@pytest.mark.asyncio
async def test_evaluate_async_arithmetic():
    """测试 evaluate_async 评估算术表达式。."""
    env = standard_environment()

    # (+ 1 2 3)
    expr = L(Symbol("+"), 1, 2, 3)
    result = await evaluate_async(expr, env)
    assert result == 6


@pytest.mark.asyncio
async def test_evaluate_async_nested_expression():
    """测试 evaluate_async 评估嵌套表达式。."""
    env = standard_environment()

    # (+ (* 2 3) (- 10 5))
    expr = L(Symbol("+"), L(Symbol("*"), 2, 3), L(Symbol("-"), 10, 5))
    result = await evaluate_async(expr, env)
    assert result == 11


@pytest.mark.asyncio
async def test_evaluate_async_let_binding():
    """测试 evaluate_async 评估 let 绑定。."""
    env = standard_environment()

    # (let ((x 10) (y 20)) (+ x y))
    expr = L(
        Symbol("let"),
        L(L(Symbol("x"), 10), L(Symbol("y"), 20)),
        L(Symbol("+"), Symbol("x"), Symbol("y")),
    )
    result = await evaluate_async(expr, env)
    assert result == 30


@pytest.mark.asyncio
async def test_evaluate_body_async_single_expression():
    """测试 evaluate_body_async 评估单个表达式。."""
    env = standard_environment()

    body = (L(Symbol("+"), 1, 2),)
    result = await evaluate_body_async(body, env)
    assert result == 3


@pytest.mark.asyncio
async def test_evaluate_body_async_multiple_expressions():
    """测试 evaluate_body_async 评估多个表达式并返回最后一个。."""
    env = standard_environment()

    # (define x 10)
    # (define y 20)
    # (+ x y)
    body = (
        L(Symbol("define"), Symbol("x"), 10),
        L(Symbol("define"), Symbol("y"), 20),
        L(Symbol("+"), Symbol("x"), Symbol("y")),
    )
    result = await evaluate_body_async(body, env)
    assert result == 30
    assert env.resolve(Symbol("x")) == 10
    assert env.resolve(Symbol("y")) == 20


@pytest.mark.asyncio
async def test_evaluate_body_async_empty_body_raises_error():
    """测试 evaluate_body_async 对空 body 抛出错误。."""
    env = standard_environment()

    with pytest.raises(QyArityError) as exc_info:
        await evaluate_body_async((), env)

    assert "body must contain at least one expression" in str(exc_info.value)


@pytest.mark.asyncio
async def test_evaluate_async_with_effects():
    """测试 evaluate_async 与代数效应的集成。."""
    env = standard_environment()

    # 使用正确的 handle 语法：(handle body ((effect (arg k) handler-body)))
    source = """
    (defeffect ask)
    (handle
      (+ 1 (perform ask 41))
      ((ask (arg k) (resume k arg))))
    """
    forms = read(source)

    # 先定义 effect
    await evaluate_async(forms[0], env)
    # 然后执行 handle
    result = await evaluate_async(forms[1], env)
    assert result == 42


@pytest.mark.asyncio
async def test_evaluate_body_async_with_effects():
    """测试 evaluate_body_async 与代数效应的集成。."""
    env = standard_environment()

    source = """
    (defeffect ask)
    (define result
      (handle
        (+ 10 (perform ask 5))
        ((ask (arg k) (resume k arg)))))
    """
    forms = read(source)
    body = tuple(forms)

    await evaluate_body_async(body, env)
    assert env.resolve(Symbol("result")) == 15


@pytest.mark.asyncio
async def test_evaluate_async_lambda_and_call():
    """测试 evaluate_async 评估 lambda 和函数调用。."""
    env = standard_environment()

    # ((lambda (x y) (+ x y)) 10 20)
    expr = L(
        L(Symbol("lambda"), L(Symbol("x"), Symbol("y")), L(Symbol("+"), Symbol("x"), Symbol("y"))),
        10,
        20,
    )
    result = await evaluate_async(expr, env)
    assert result == 30


@pytest.mark.asyncio
async def test_evaluate_async_defun_and_call():
    """测试 evaluate_async 评估 defun 和函数调用。."""
    env = standard_environment()

    # (defun add (x y) (+ x y))
    # (add 10 20)
    defun_expr = L(
        Symbol("defun"),
        Symbol("add"),
        L(Symbol("x"), Symbol("y")),
        L(Symbol("+"), Symbol("x"), Symbol("y")),
    )
    await evaluate_async(defun_expr, env)

    call_expr = L(Symbol("add"), 10, 20)
    result = await evaluate_async(call_expr, env)
    assert result == 30


@pytest.mark.asyncio
async def test_evaluate_body_async_preserves_environment():
    """测试 evaluate_body_async 保持环境状态。."""
    env = standard_environment()

    body = (
        L(Symbol("define"), Symbol("a"), 1),
        L(Symbol("define"), Symbol("b"), 2),
        L(Symbol("define"), Symbol("c"), 3),
    )

    await evaluate_body_async(body, env)

    assert env.resolve(Symbol("a")) == 1
    assert env.resolve(Symbol("b")) == 2
    assert env.resolve(Symbol("c")) == 3


@pytest.mark.asyncio
async def test_evaluate_async_quote():
    """测试 evaluate_async 评估 quote。."""
    from qy.core.syntax import Chain as QyChain

    env = standard_environment()

    # (quote (+ 1 2))
    expr = L(Symbol("quote"), L(Symbol("+"), 1, 2))
    result = await evaluate_async(expr, env)

    # quote 应该返回未求值的表达式（作为 QyChain）
    assert isinstance(result, QyChain)
    assert result.head == Symbol("+")


@pytest.mark.asyncio
async def test_evaluate_async_with_recursive_function():
    """递归函数经 register VM 求值的完整集成。."""
    env = standard_environment()

    # 定义一个简单的递归函数，使用 (= 1 1) 作为 else 条件
    source = """
    (defun factorial (n)
      (cond
        ((= n 0) 1)
        ((= 1 1) (* n (factorial (- n 1))))))
    (factorial 5)
    """
    forms = read(source)

    # 定义函数
    await evaluate_async(forms[0], env)
    # 调用函数
    result = await evaluate_async(forms[1], env)
    assert result == 120
