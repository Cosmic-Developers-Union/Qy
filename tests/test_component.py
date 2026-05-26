# coding: utf-8

import pytest

from qy.import_.registry import standard_bindings
from qy.runtime import evaluate_source
from qy.session.runtime_space import RuntimeSpace as Environment


def _env() -> Environment:
    return Environment(standard_bindings(("qy.core",)))


def es(source: str) -> object:
    return evaluate_source(source, _env())


def test_component_define_lambda():
    """测试 component 组合 define 和 lambda。."""
    code = """
    (define defun-component (component define lambda))
    (defun-component add (a b) (+ a b))
    (add 3 4)
    """
    result = es(code)
    assert result == 7


def test_component_basic():
    """测试 component 的基本功能。."""
    # 测试 (component define lambda) 等价于手动定义
    code1 = """
    (define defun-component (component define lambda))
    (defun-component simple-01 () (+ 1 2))
    (simple-01)
    """
    result1 = es(code1)
    assert result1 == 3

    # 验证等价于标准定义
    code2 = """
    (define simple-02 (lambda () (+ 1 2)))
    (simple-02)
    """
    result2 = es(code2)
    assert result2 == 3


def test_component_with_parameters():
    """测试 component 定义的函数可以接收参数。."""
    code = """
    (define defun-component (component define lambda))
    (defun-component multiply (x y) (* x y))
    (multiply 5 6)
    """
    result = es(code)
    assert result == 30


def test_component_multiple_body_expressions():
    """测试 component 定义的函数可以有多个 body 表达式。."""
    code = """
    (define defun-component (component define lambda))
    (defun-component compute (x)
      (define temp (+ x 1))
      (* temp 2))
    (compute 5)
    """
    result = es(code)
    assert result == 12


def test_component_arity_error():
    """测试 component 需要至少 2 个算子。."""
    from qy.errors import QyRuntimeError

    code = "(component define)"
    with pytest.raises(QyRuntimeError, match="at least 2 operators"):
        es(code)


def test_component_closure():
    """测试 component 定义的函数正确捕获闭包。."""
    code = """
    (define defun-component (component define lambda))
    (define x 10)
    (defun-component use-closure (y) (+ x y))
    (use-closure 5)
    """
    result = es(code)
    assert result == 15
