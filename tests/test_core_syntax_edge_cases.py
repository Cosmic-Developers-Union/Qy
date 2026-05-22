# coding: utf-8
"""测试 qy.core.syntax 模块的边界情况。."""

from __future__ import annotations

import pytest

from qy.core.syntax import cons
from qy.core.syntax import nil
from qy.frontend.reader import Symbol


def test_chain_iter_improper_list():
    """测试迭代 improper list 抛出异常。."""
    # 创建 improper list: (a . b)
    improper = cons(Symbol("a"), Symbol("b"))

    # 直接使用 iter() 而不是 list()，以触发 __iter__ 的异常路径
    iterator = iter(improper)
    assert next(iterator) == Symbol("a")

    with pytest.raises(ValueError) as exc_info:
        next(iterator)

    assert "Cannot iterate improper list" in str(exc_info.value)


def test_chain_len_improper_list():
    """测试计算 improper list 长度抛出异常。."""
    # 创建 improper list: (a . b)
    improper = cons(Symbol("a"), Symbol("b"))

    with pytest.raises(ValueError) as exc_info:
        len(improper)

    assert "Cannot get length of improper list" in str(exc_info.value)


def test_chain_iter_proper_list():
    """测试迭代 proper list。."""
    # 创建 proper list: (a b c)
    chain = cons(Symbol("a"), cons(Symbol("b"), cons(Symbol("c"), nil)))

    items = list(chain)
    assert len(items) == 3
    assert items[0] == Symbol("a")
    assert items[1] == Symbol("b")
    assert items[2] == Symbol("c")


def test_chain_len_proper_list():
    """测试计算 proper list 长度。."""
    # 创建 proper list: (a b c)
    chain = cons(Symbol("a"), cons(Symbol("b"), cons(Symbol("c"), nil)))

    assert len(chain) == 3
