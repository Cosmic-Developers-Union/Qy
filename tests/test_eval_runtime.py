# coding: utf-8
"""测试 qy.eval_runtime 模块的迁移后功能。.

这个模块测试 eval_runtime.py 从旧的 evaluator 模块迁移到
register_vm 后的正确性。
"""

from __future__ import annotations

import pytest

from qy.environment import standard_environment
from qy.errors import QyArityError
from qy.eval_runtime import evaluate_async
from qy.eval_runtime import evaluate_body_async
from qy.eval_runtime import evaluate_tail_body_async
from qy.frontend.reader import Symbol
from qy.frontend.reader import read
from qy.sem.runtime import UserFunction
from qy.values import QY_NIL
from qy.vm.instance.values import TailCall


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
    expr = (Symbol("+"), 1, 2, 3)
    result = await evaluate_async(expr, env)
    assert result == 6


@pytest.mark.asyncio
async def test_evaluate_async_nested_expression():
    """测试 evaluate_async 评估嵌套表达式。."""
    env = standard_environment()

    # (+ (* 2 3) (- 10 5))
    expr = (Symbol("+"), (Symbol("*"), 2, 3), (Symbol("-"), 10, 5))
    result = await evaluate_async(expr, env)
    assert result == 11


@pytest.mark.asyncio
async def test_evaluate_async_let_binding():
    """测试 evaluate_async 评估 let 绑定。."""
    env = standard_environment()

    # (let ((x 10) (y 20)) (+ x y))
    expr = (
        Symbol("let"),
        ((Symbol("x"), 10), (Symbol("y"), 20)),
        (Symbol("+"), Symbol("x"), Symbol("y")),
    )
    result = await evaluate_async(expr, env)
    assert result == 30


@pytest.mark.asyncio
async def test_evaluate_body_async_single_expression():
    """测试 evaluate_body_async 评估单个表达式。."""
    env = standard_environment()

    body = ((Symbol("+"), 1, 2),)
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
        (Symbol("define"), Symbol("x"), 10),
        (Symbol("define"), Symbol("y"), 20),
        (Symbol("+"), Symbol("x"), Symbol("y")),
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
async def test_evaluate_tail_body_async_simple():
    """测试 evaluate_tail_body_async 评估简单函数体。."""
    env = standard_environment()
    func = UserFunction(
        name=Symbol("test"),
        params=(Symbol("x"),),
        body=((Symbol("+"), Symbol("x"), 1),),
        closure=env,
    )
    env.define(Symbol("x"), 10)

    result = await evaluate_tail_body_async(func.body, env, func)
    assert result == 11


@pytest.mark.asyncio
async def test_evaluate_tail_body_async_multiple_expressions():
    """测试 evaluate_tail_body_async 评估多个表达式。."""
    env = standard_environment()
    func = UserFunction(
        name=Symbol("test"),
        params=(Symbol("x"),),
        body=(
            (Symbol("define"), Symbol("y"), 5),
            (Symbol("+"), Symbol("x"), Symbol("y")),
        ),
        closure=env,
    )
    env.define(Symbol("x"), 10)

    result = await evaluate_tail_body_async(func.body, env, func)
    assert result == 15


@pytest.mark.asyncio
async def test_evaluate_tail_body_async_self_tail_call():
    """测试 evaluate_tail_body_async 识别自尾调用。."""
    env = standard_environment()

    # 创建一个递归函数
    func = UserFunction(
        name=Symbol("countdown"),
        params=(Symbol("n"),),
        body=((Symbol("countdown"), (Symbol("-"), Symbol("n"), 1)),),
        closure=env,
    )
    env.define(Symbol("countdown"), func)
    env.define(Symbol("n"), 5)

    # 这应该返回 TailCall 而不是实际执行递归
    result = await evaluate_tail_body_async(func.body, env, func)
    assert isinstance(result, TailCall)
    assert result.function is func


@pytest.mark.asyncio
async def test_evaluate_tail_body_async_cond_in_tail_position():
    """测试 evaluate_tail_body_async 处理尾位置的 cond。."""
    env = standard_environment()

    # 使用 = 而不是 > 因为 > 可能未定义
    func = UserFunction(
        name=Symbol("test"),
        params=(Symbol("x"),),
        body=(
            (
                Symbol("cond"),
                ((Symbol("="), Symbol("x"), 15), Symbol("x")),
                ((Symbol("="), 1, 1), 0),  # 使用 (= 1 1) 作为 true 条件
            ),
        ),
        closure=env,
    )
    env.define(Symbol("x"), 15)

    result = await evaluate_tail_body_async(func.body, env, func)
    assert result == 15


@pytest.mark.asyncio
async def test_evaluate_tail_body_async_cond_returns_nil_when_no_match():
    """测试 evaluate_tail_body_async 的 cond 在无匹配时返回 nil。."""
    env = standard_environment()
    func = UserFunction(
        name=Symbol("test"),
        params=(Symbol("x"),),
        body=(
            (
                Symbol("cond"),
                ((Symbol("="), Symbol("x"), 100), Symbol("x")),  # 条件不满足
            ),
        ),
        closure=env,
    )
    env.define(Symbol("x"), 5)

    result = await evaluate_tail_body_async(func.body, env, func)
    assert result is QY_NIL


@pytest.mark.asyncio
async def test_evaluate_tail_body_async_let_in_tail_position():
    """测试 evaluate_tail_body_async 处理尾位置的 let。."""
    env = standard_environment()
    func = UserFunction(
        name=Symbol("test"),
        params=(Symbol("x"),),
        body=(
            (
                Symbol("let"),
                ((Symbol("y"), 10),),
                (Symbol("+"), Symbol("x"), Symbol("y")),
            ),
        ),
        closure=env,
    )
    env.define(Symbol("x"), 5)

    result = await evaluate_tail_body_async(func.body, env, func)
    assert result == 15


@pytest.mark.asyncio
async def test_evaluate_tail_body_async_empty_body_raises_error():
    """测试 evaluate_tail_body_async 对空 body 抛出错误。."""
    env = standard_environment()
    func = UserFunction(
        name=Symbol("test"),
        params=(),
        body=(),
        closure=env,
    )

    with pytest.raises(QyArityError) as exc_info:
        await evaluate_tail_body_async((), env, func)

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
    expr = (
        (Symbol("lambda"), (Symbol("x"), Symbol("y")), (Symbol("+"), Symbol("x"), Symbol("y"))),
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
    defun_expr = (
        Symbol("defun"),
        Symbol("add"),
        (Symbol("x"), Symbol("y")),
        (Symbol("+"), Symbol("x"), Symbol("y")),
    )
    await evaluate_async(defun_expr, env)

    call_expr = (Symbol("add"), 10, 20)
    result = await evaluate_async(call_expr, env)
    assert result == 30


@pytest.mark.asyncio
async def test_evaluate_body_async_preserves_environment():
    """测试 evaluate_body_async 保持环境状态。."""
    env = standard_environment()

    body = (
        (Symbol("define"), Symbol("a"), 1),
        (Symbol("define"), Symbol("b"), 2),
        (Symbol("define"), Symbol("c"), 3),
    )

    await evaluate_body_async(body, env)

    assert env.resolve(Symbol("a")) == 1
    assert env.resolve(Symbol("b")) == 2
    assert env.resolve(Symbol("c")) == 3


@pytest.mark.asyncio
async def test_evaluate_async_quote():
    """测试 evaluate_async 评估 quote。."""
    from qy.values import QyChain

    env = standard_environment()

    # (quote (+ 1 2))
    expr = (Symbol("quote"), (Symbol("+"), 1, 2))
    result = await evaluate_async(expr, env)

    # quote 应该返回未求值的表达式（作为 QyChain）
    assert isinstance(result, QyChain)
    assert result.head == Symbol("+")


@pytest.mark.asyncio
async def test_evaluate_tail_body_async_with_recursive_function():
    """测试 evaluate_tail_body_async 与递归函数的完整集成。."""
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
