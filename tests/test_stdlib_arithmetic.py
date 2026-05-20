# coding: utf-8
"""测试 qy.stdlib.arithmetic 模块。."""

from __future__ import annotations

import pytest

from qy.errors import QyTypeError
from qy.stdlib.arithmetic import _add
from qy.stdlib.arithmetic import _div
from qy.stdlib.arithmetic import _ensure_number
from qy.stdlib.arithmetic import _mul
from qy.stdlib.arithmetic import _num_eq
from qy.stdlib.arithmetic import _py_eq
from qy.stdlib.arithmetic import _sub
from qy.values import QY_NIL
from qy.values import QY_T


def test_ensure_number_with_int():
    """测试 _ensure_number 接受整数。."""
    assert _ensure_number(42) == 42


def test_ensure_number_with_float():
    """测试 _ensure_number 接受浮点数。."""
    assert _ensure_number(3.14) == 3.14


def test_ensure_number_with_bool_raises_error():
    """测试 _ensure_number 拒绝布尔值。."""
    with pytest.raises(QyTypeError) as exc_info:
        _ensure_number(True)
    assert "expected number" in str(exc_info.value)


def test_ensure_number_with_string_raises_error():
    """测试 _ensure_number 拒绝字符串。."""
    with pytest.raises(QyTypeError):
        _ensure_number("not a number")


def test_py_eq_equal_values():
    """测试 _py_eq 比较相等的值。."""
    assert _py_eq(42, 42) is QY_T
    assert _py_eq("hello", "hello") is QY_T


def test_py_eq_unequal_values():
    """测试 _py_eq 比较不相等的值。."""
    assert _py_eq(42, 43) is QY_NIL
    assert _py_eq("hello", "world") is QY_NIL


def test_num_eq_with_bools():
    """测试 _num_eq 比较布尔值使用 is。."""
    assert _num_eq(True, True) is QY_T
    assert _num_eq(False, False) is QY_T
    assert _num_eq(True, False) is QY_NIL


def test_num_eq_with_numbers():
    """测试 _num_eq 比较数字。."""
    assert _num_eq(42, 42) is QY_T
    assert _num_eq(3.14, 3.14) is QY_T
    assert _num_eq(42, 43) is QY_NIL


def test_num_eq_with_non_numbers():
    """测试 _num_eq 比较非数字使用 is。."""
    obj = object()
    assert _num_eq(obj, obj) is QY_T
    assert _num_eq(object(), object()) is QY_NIL


def test_add_multiple_numbers():
    """测试 _add 加多个数字。."""
    assert _add(1, 2, 3, 4) == 10


def test_add_no_args():
    """测试 _add 无参数返回 0。."""
    assert _add() == 0


def test_add_floats():
    """测试 _add 加浮点数。."""
    assert _add(1.5, 2.5, 3.0) == 7.0


def test_sub_single_arg():
    """测试 _sub 单参数返回负数。."""
    assert _sub(5) == -5


def test_sub_multiple_args():
    """测试 _sub 多参数减法。."""
    assert _sub(10, 3, 2) == 5


def test_mul_multiple_numbers():
    """测试 _mul 乘多个数字。."""
    assert _mul(2, 3, 4) == 24


def test_mul_no_args():
    """测试 _mul 无参数返回 1。."""
    assert _mul() == 1


def test_mul_with_floats():
    """测试 _mul 乘浮点数。."""
    assert _mul(2.5, 4) == 10.0


def test_div_single_arg():
    """测试 _div 单参数返回倒数。."""
    assert _div(4) == 0.25


def test_div_multiple_args():
    """测试 _div 多参数除法。."""
    assert _div(20, 2, 2) == 5.0


def test_div_with_floats():
    """测试 _div 除浮点数。."""
    assert _div(10.0, 2.5) == 4.0


def test_arithmetic_with_invalid_type():
    """测试算术运算拒绝无效类型。."""
    with pytest.raises(QyTypeError):
        _add(1, "not a number", 3)

    with pytest.raises(QyTypeError):
        _sub(10, "invalid")

    with pytest.raises(QyTypeError):
        _mul(2, None, 4)

    with pytest.raises(QyTypeError):
        _div(10, [])
