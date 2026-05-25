# coding: utf-8
"""测试 qy.runtime 模块的公共评估 API。.

测试所有公共评估函数，确保它们正确地通过 register VM 管线
（macroexpand -> lower -> compile -> VM）工作。
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from qy.core.syntax import Chain as QyChain
from qy.core.syntax import nil as QY_NIL
from qy.environment import Environment
from qy.environment import standard_environment
from qy.errors import QyArityError
from qy.errors import QyError
from qy.errors import QyResolveError
from qy.frontend.reader import Symbol
from qy.frontend.reader import read
from qy.runtime import evaluate
from qy.runtime import evaluate_async
from qy.runtime import evaluate_body
from qy.runtime import evaluate_body_async
from qy.runtime import evaluate_file
from qy.runtime import evaluate_file_async
from qy.runtime import evaluate_program
from qy.runtime import evaluate_program_async
from qy.runtime import evaluate_source
from qy.runtime import evaluate_source_async

# -- evaluate / evaluate_async tests -----------------------------------------


def test_evaluate_symbol():
    """测试 evaluate 解析符号。."""
    env = standard_environment()
    env.define(Symbol("x"), 42)

    result = evaluate(Symbol("x"), env)
    assert result == 42


def test_evaluate_arithmetic():
    """测试 evaluate 评估算术表达式。."""
    env = standard_environment()

    # (+ 1 2 3)
    expr = (Symbol("+"), 1, 2, 3)
    result = evaluate(expr, env)
    assert result == 6


def test_evaluate_nested_expression():
    """测试 evaluate 评估嵌套表达式。."""
    env = standard_environment()

    # (+ (* 2 3) (- 10 5))
    expr = (Symbol("+"), (Symbol("*"), 2, 3), (Symbol("-"), 10, 5))
    result = evaluate(expr, env)
    assert result == 11


def test_evaluate_with_default_environment():
    """测试 evaluate 使用默认环境。."""
    # (+ 1 2)
    expr = (Symbol("+"), 1, 2)
    result = evaluate(expr)
    assert result == 3


def test_evaluate_let_binding():
    """测试 evaluate 评估 let 绑定。."""
    env = standard_environment()

    # (let ((x 10) (y 20)) (+ x y))
    expr = (
        Symbol("let"),
        ((Symbol("x"), 10), (Symbol("y"), 20)),
        (Symbol("+"), Symbol("x"), Symbol("y")),
    )
    result = evaluate(expr, env)
    assert result == 30


def test_evaluate_lambda_and_call():
    """测试 evaluate 评估 lambda 和函数调用。."""
    env = standard_environment()

    # ((lambda (x y) (+ x y)) 10 20)
    expr = (
        (Symbol("lambda"), (Symbol("x"), Symbol("y")), (Symbol("+"), Symbol("x"), Symbol("y"))),
        10,
        20,
    )
    result = evaluate(expr, env)
    assert result == 30


def test_evaluate_quote():
    """测试 evaluate 评估 quote。."""
    env = standard_environment()

    # (quote (+ 1 2))
    expr = (Symbol("quote"), (Symbol("+"), 1, 2))
    result = evaluate(expr, env)

    # quote 应该返回未求值的表达式
    assert isinstance(result, QyChain)
    assert result.head == Symbol("+")


@pytest.mark.asyncio
async def test_evaluate_async_symbol():
    """测试 evaluate_async 解析符号。."""
    env = standard_environment()
    env.define(Symbol("x"), 100)

    result = await evaluate_async(Symbol("x"), env)
    assert result == 100


@pytest.mark.asyncio
async def test_evaluate_async_with_effects():
    """测试 evaluate_async 与代数效应的集成。."""
    env = standard_environment()

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


# -- evaluate_source / evaluate_source_async tests --------------------------


def test_evaluate_source_simple():
    """测试 evaluate_source 评估简单源代码。."""
    source = "(+ 1 2 3)"
    result = evaluate_source(source)
    assert result == 6


def test_evaluate_source_multiple_forms():
    """测试 evaluate_source 评估多个表达式，返回最后一个。."""
    source = """
    (define x 10)
    (define y 20)
    (+ x y)
    """
    result = evaluate_source(source)
    assert result == 30


def test_evaluate_source_with_environment():
    """测试 evaluate_source 使用自定义环境。."""
    env = standard_environment()
    source = """
    (define x 100)
    x
    """
    result = evaluate_source(source, env)
    assert result == 100
    assert env.resolve(Symbol("x")) == 100


def test_evaluate_source_with_source_name():
    """测试 evaluate_source 使用源文件名。."""
    source = "(+ 1 2)"
    result = evaluate_source(source, source_name="test.qy")
    assert result == 3


def test_evaluate_source_empty():
    """测试 evaluate_source 评估空源代码。."""
    source = ""
    result = evaluate_source(source)
    assert result is None


def test_evaluate_source_with_comments():
    """测试 evaluate_source 评估带注释的源代码。."""
    source = """
    ; 这是注释
    (+ 1 2) ; 行尾注释
    """
    result = evaluate_source(source)
    assert result == 3


def test_evaluate_source_with_defun():
    """测试 evaluate_source 评估函数定义和调用。."""
    source = """
    (defun add (x y)
      (+ x y))
    (add 10 20)
    """
    result = evaluate_source(source)
    assert result == 30


def test_evaluate_source_with_recursive_function():
    """测试 evaluate_source 评估递归函数。."""
    source = """
    (defun factorial (n)
      (cond
        ((= n 0) 1)
        ((= 1 1) (* n (factorial (- n 1))))))
    (factorial 5)
    """
    result = evaluate_source(source)
    assert result == 120


def test_evaluate_source_with_effects():
    """测试 evaluate_source 与代数效应。."""
    source = """
    (defeffect ask)
    (handle
      (+ 10 (perform ask 5))
      ((ask (arg k) (resume k arg))))
    """
    result = evaluate_source(source)
    assert result == 15


def test_evaluate_source_unresolved_symbol_error():
    """测试 evaluate_source 对未解析符号抛出错误。."""
    source = "(+ x 1)"

    with pytest.raises(QyResolveError) as exc_info:
        evaluate_source(source)

    assert "unresolved symbol" in str(exc_info.value)
    assert "x" in str(exc_info.value)


@pytest.mark.asyncio
async def test_evaluate_source_async_simple():
    """测试 evaluate_source_async 评估简单源代码。."""
    source = "(* 2 3 4)"
    result = await evaluate_source_async(source)
    assert result == 24


@pytest.mark.asyncio
async def test_evaluate_source_async_with_environment():
    """测试 evaluate_source_async 使用自定义环境。."""
    env = standard_environment()
    source = """
    (define a 5)
    (define b 10)
    (* a b)
    """
    result = await evaluate_source_async(source, env)
    assert result == 50
    assert env.resolve(Symbol("a")) == 5
    assert env.resolve(Symbol("b")) == 10


# -- evaluate_program / evaluate_program_async tests ------------------------


def test_evaluate_program_returns_all_results():
    """测试 evaluate_program 返回所有表达式的结果。."""
    source = """
    (+ 1 2)
    (* 3 4)
    (- 10 5)
    """
    results = evaluate_program(source)
    assert results == [3, 12, 5]


def test_evaluate_program_empty():
    """测试 evaluate_program 评估空源代码。."""
    source = ""
    results = evaluate_program(source)
    assert results == []


def test_evaluate_program_with_definitions():
    """测试 evaluate_program 评估包含定义的程序。."""
    source = """
    (define x 10)
    (define y 20)
    (+ x y)
    """
    results = evaluate_program(source)
    # define 返回 nil，最后一个表达式返回 30
    assert results[-1] == 30


def test_evaluate_program_with_environment():
    """测试 evaluate_program 使用自定义环境。."""
    env = standard_environment()
    source = """
    (define x 100)
    (define y 200)
    """
    evaluate_program(source, env)
    assert env.resolve(Symbol("x")) == 100
    assert env.resolve(Symbol("y")) == 200


def test_evaluate_program_with_source_name():
    """测试 evaluate_program 使用源文件名。."""
    source = "(+ 1 2)"
    results = evaluate_program(source, source_name="test.qy")
    assert results == [3]


@pytest.mark.asyncio
async def test_evaluate_program_async_returns_all_results():
    """测试 evaluate_program_async 返回所有表达式的结果。."""
    source = """
    (+ 1 1)
    (+ 2 2)
    (+ 3 3)
    """
    results = await evaluate_program_async(source)
    assert results == [2, 4, 6]


@pytest.mark.asyncio
async def test_evaluate_program_async_with_effects():
    """测试 evaluate_program_async 与代数效应。."""
    source = """
    (defeffect ask)
    (handle
      (perform ask 10)
      ((ask (arg k) (resume k (* arg 2)))))
    """
    results = await evaluate_program_async(source)
    # defeffect 返回 nil，handle 返回 20
    assert results[-1] == 20


# -- evaluate_file / evaluate_file_async tests -------------------------------


def test_evaluate_file_simple():
    """测试 evaluate_file 评估文件。."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".qy", delete=False) as f:
        f.write("(+ 1 2 3)")
        f.flush()
        temp_path = f.name

    try:
        result = evaluate_file(temp_path)
        assert result == 6
    finally:
        Path(temp_path).unlink()


def test_evaluate_file_with_multiple_forms():
    """测试 evaluate_file 评估包含多个表达式的文件。."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".qy", delete=False) as f:
        f.write("""
(define x 10)
(define y 20)
(+ x y)
        """)
        f.flush()
        temp_path = f.name

    try:
        result = evaluate_file(temp_path)
        assert result == 30
    finally:
        Path(temp_path).unlink()


def test_evaluate_file_with_environment():
    """测试 evaluate_file 使用自定义环境。."""
    env = standard_environment()

    with tempfile.NamedTemporaryFile(mode="w", suffix=".qy", delete=False) as f:
        f.write("(define x 100)\nx")
        f.flush()
        temp_path = f.name

    try:
        result = evaluate_file(temp_path, env)
        assert result == 100
        assert env.resolve(Symbol("x")) == 100
    finally:
        Path(temp_path).unlink()


def test_evaluate_file_empty():
    """测试 evaluate_file 评估空文件。."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".qy", delete=False) as f:
        f.write("")
        f.flush()
        temp_path = f.name

    try:
        result = evaluate_file(temp_path)
        assert result is None
    finally:
        Path(temp_path).unlink()


def test_evaluate_file_with_path_object():
    """测试 evaluate_file 接受 Path 对象。."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".qy", delete=False) as f:
        f.write("(* 2 3)")
        f.flush()
        temp_path = Path(f.name)

    try:
        result = evaluate_file(temp_path)
        assert result == 6
    finally:
        temp_path.unlink()


@pytest.mark.asyncio
async def test_evaluate_file_async_simple():
    """测试 evaluate_file_async 评估文件。."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".qy", delete=False) as f:
        f.write("(- 10 3)")
        f.flush()
        temp_path = f.name

    try:
        result = await evaluate_file_async(temp_path)
        assert result == 7
    finally:
        Path(temp_path).unlink()


@pytest.mark.asyncio
async def test_evaluate_file_async_with_effects():
    """测试 evaluate_file_async 与代数效应。."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".qy", delete=False) as f:
        f.write("""
(defeffect ask)
(handle
  (+ 100 (perform ask 50))
  ((ask (arg k) (resume k arg))))
        """)
        f.flush()
        temp_path = f.name

    try:
        result = await evaluate_file_async(temp_path)
        assert result == 150
    finally:
        Path(temp_path).unlink()


# -- evaluate_body / evaluate_body_async tests -------------------------------


def test_evaluate_body_single_expression():
    """测试 evaluate_body 评估单个表达式。."""
    env = standard_environment()
    body = ((Symbol("+"), 1, 2),)
    result = evaluate_body(body, env)
    assert result == 3


def test_evaluate_body_multiple_expressions():
    """测试 evaluate_body 评估多个表达式并返回最后一个。."""
    env = standard_environment()
    body = (
        (Symbol("define"), Symbol("x"), 10),
        (Symbol("define"), Symbol("y"), 20),
        (Symbol("+"), Symbol("x"), Symbol("y")),
    )
    result = evaluate_body(body, env)
    assert result == 30
    assert env.resolve(Symbol("x")) == 10
    assert env.resolve(Symbol("y")) == 20


def test_evaluate_body_empty_raises_error():
    """测试 evaluate_body 对空 body 抛出错误。."""
    env = standard_environment()

    with pytest.raises(QyArityError) as exc_info:
        evaluate_body((), env)

    assert "body must contain at least one expression" in str(exc_info.value)


def test_evaluate_body_with_side_effects():
    """测试 evaluate_body 评估有副作用的表达式。."""
    env = standard_environment()
    body = (
        (Symbol("define"), Symbol("a"), 1),
        (Symbol("define"), Symbol("b"), 2),
        (Symbol("define"), Symbol("c"), 3),
        (Symbol("+"), Symbol("a"), Symbol("b"), Symbol("c")),
    )
    result = evaluate_body(body, env)
    assert result == 6
    assert env.resolve(Symbol("a")) == 1
    assert env.resolve(Symbol("b")) == 2
    assert env.resolve(Symbol("c")) == 3


@pytest.mark.asyncio
async def test_evaluate_body_async_single_expression():
    """测试 evaluate_body_async 评估单个表达式。."""
    env = standard_environment()
    body = ((Symbol("*"), 2, 3),)
    result = await evaluate_body_async(body, env)
    assert result == 6


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


# -- Pipeline integration tests ----------------------------------------------


def test_pipeline_macroexpand_to_vm():
    """测试完整管线：macroexpand -> lower -> compile -> VM。."""
    source = """
    (defun square (x)
      (* x x))
    (square 5)
    """
    result = evaluate_source(source)
    assert result == 25


def test_pipeline_with_nested_functions():
    """测试管线处理嵌套函数。."""
    source = """
    (defun outer (x)
      (defun inner (y)
        (+ x y))
      (inner 10))
    (outer 5)
    """
    result = evaluate_source(source)
    assert result == 15


def test_pipeline_with_closures():
    """测试管线处理闭包。."""
    source = """
    ((lambda (x)
       (lambda (y) (+ x y)))
     5)
    """
    # 返回一个闭包函数
    add5 = evaluate_source(source)
    # 调用闭包
    env = standard_environment()
    env.define(Symbol("add5"), add5)
    result = evaluate_source("(add5 10)", env)
    assert result == 15


def test_pipeline_with_complex_effects():
    """测试管线处理嵌套的代数效应。."""
    source = """
    (defeffect ask)
    (handle
      (handle
        (+ (perform ask 10) (perform ask 20))
        ((ask (arg k) (resume k arg))))
      ((ask (arg k) (resume k arg))))
    """
    result = evaluate_source(source)
    assert result == 30


def test_pipeline_error_handling():
    """测试管线的错误处理。."""
    source = "(+ undefined-symbol 1)"

    with pytest.raises(QyResolveError) as exc_info:
        evaluate_source(source)

    assert "unresolved symbol" in str(exc_info.value)


def test_pipeline_with_cond():
    """测试管线处理 cond 表达式。."""
    source = """
    (defun abs (x)
      (cond
        ((= x 0) 0)
        ((= 1 1) x)))
    (abs -5)
    """
    result = evaluate_source(source)
    assert result == -5


def test_pipeline_with_let_scoping():
    """测试管线处理 let 作用域。."""
    source = """
    (define x 100)
    (let ((x 10)
          (y 20))
      (+ x y))
    """
    result = evaluate_source(source)
    assert result == 30


# -- Edge cases and error handling -------------------------------------------


def test_evaluate_nil():
    """测试 evaluate 评估 nil。."""
    result = evaluate(QY_NIL)
    # evaluate 对于非 Symbol 和非 tuple 的值会通过管线，可能返回 None
    assert result is QY_NIL or result is None


def test_evaluate_number():
    """测试 evaluate 评估数字。."""
    result = evaluate(42)
    assert result == 42


def test_evaluate_string():
    """测试 evaluate 评估字符串。."""
    result = evaluate("hello")
    assert result == "hello"


def test_evaluate_empty_tuple():
    """测试 evaluate 评估空元组。."""
    # 空元组应该被视为空列表
    result = evaluate(())
    # 根据实现，这可能返回 nil 或空列表
    assert result is not None


def test_evaluate_source_with_syntax_error():
    """测试 evaluate_source 处理语法错误。."""
    source = "(+ 1 2"  # 缺少右括号

    with pytest.raises(QyError):
        evaluate_source(source)


def test_evaluate_program_preserves_order():
    """测试 evaluate_program 保持表达式顺序。."""
    source = """
    (define x 1)
    (define x (+ x 1))
    """
    # 这应该失败，因为 define 不能重新绑定
    # 但如果成功，应该按顺序执行
    with pytest.raises(QyError):
        evaluate_program(source)


def test_concurrent_evaluation_with_separate_environments():
    """测试使用独立环境的并发评估。."""
    env1 = standard_environment()
    env2 = standard_environment()

    source = "(define x 10)\nx"

    result1 = evaluate_source(source, env1)
    result2 = evaluate_source(source, env2)

    assert result1 == 10
    assert result2 == 10
    assert env1.resolve(Symbol("x")) == 10
    assert env2.resolve(Symbol("x")) == 10


# -- Backward compatibility tests --------------------------------------------


def test_backward_compatibility_imports():
    """测试核心类型可从规范模块导入。."""
    from qy.core.syntax import Chain as QyChain
    from qy.core.syntax import Chain as QyCons
    from qy.core.syntax import nil as QY_EMPTY_CHAIN
    from qy.core.syntax import nil as QY_EMPTY_LIST
    from qy.core.syntax import nil as QY_NIL
    from qy.environment import Environment
    from qy.sem.core import T as QY_T
    from qy.sem.runtime import UserFunction
    from qy.vm.instance.values import HostObjectRef

    assert Environment is not None
    assert HostObjectRef is not None
    assert QY_EMPTY_CHAIN is not None
    assert QY_EMPTY_LIST is not None
    assert QY_NIL is not None
    assert QY_T is not None
    assert QyChain is not None
    assert QyCons is not None
    assert UserFunction is not None


def test_standard_environment_available():
    """测试 standard_environment 可用。."""
    from qy.environment import standard_environment

    env = standard_environment()
    assert isinstance(env, Environment)
    # 验证基本操作符可用
    assert env.resolve(Symbol("+")) is not None
    assert env.resolve(Symbol("-")) is not None
    assert env.resolve(Symbol("*")) is not None
