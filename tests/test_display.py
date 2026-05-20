# coding: utf-8
"""测试 qy.display 模块。."""

from __future__ import annotations

from qy.core.syntax import list_to_chain
from qy.display import format_value
from qy.reader import Symbol
from qy.values import QY_EMPTY_LIST
from qy.values import QY_NIL
from qy.values import QY_T
from qy.values import QyCons


def test_format_value_nil():
    """测试格式化 NIL。."""
    assert format_value(QY_NIL) == "nil"


def test_format_value_t():
    """测试格式化 T。."""
    assert format_value(QY_T) == "T"


def test_format_value_symbol():
    """测试格式化 Symbol。."""
    assert format_value(Symbol("test")) == "test"


def test_format_value_int():
    """测试格式化整数。."""
    assert format_value(42) == "42"


def test_format_value_float():
    """测试格式化浮点数。."""
    assert format_value(3.14) == "3.14"


def test_format_value_string():
    """测试格式化字符串。."""
    assert format_value("hello") == "hello"


def test_format_value_bool():
    """测试格式化布尔值。."""
    assert format_value(True) == "true"
    assert format_value(False) == "false"


def test_format_value_none():
    """测试格式化 None。."""
    assert format_value(None) == "none"


def test_format_value_cons_list():
    """测试格式化 QyCons 列表。."""
    cons = QyCons(1, QyCons(2, QyCons(3, QY_EMPTY_LIST)))
    result = format_value(cons)
    assert result == "(1 2 3)"


def test_format_value_cons_improper():
    """测试格式化不完整的 QyCons。."""
    cons = QyCons(1, QyCons(2, 3))
    result = format_value(cons)
    assert result == "(1 2 . 3)"


def test_format_value_chain():
    """测试格式化 Chain。."""
    chain = list_to_chain([1, 2, 3])
    result = format_value(chain)
    assert result == "(1 2 3)"


def test_format_value_chain_improper():
    """测试格式化不完整的 Chain。."""
    from qy.core.syntax import Chain

    chain = Chain(1, Chain(2, 3))
    result = format_value(chain)
    assert result == "(1 2 . 3)"


def test_format_value_list():
    """测试格式化 Python list。."""
    result = format_value([1, 2, 3])
    assert result == "[1 2 3]"


def test_format_value_dict():
    """测试格式化 Python dict。."""
    result = format_value({"a": 1, "b": 2})
    # Dict 顺序可能不同，检查包含关系
    assert result.startswith("{")
    assert result.endswith("}")
    assert "a 1" in result
    assert "b 2" in result


def test_format_value_set():
    """测试格式化 Python set。."""
    result = format_value({1, 2, 3})
    assert result == "#{1 2 3}"


def test_format_value_tuple():
    """测试格式化 tuple。."""
    result = format_value((Symbol("quote"), Symbol("x")))
    assert result == "(quote x)"


def test_format_value_nested():
    """测试格式化嵌套结构。."""
    nested = QyCons(
        Symbol("let"),
        QyCons(
            QyCons(Symbol("x"), QyCons(42, QY_EMPTY_LIST)),
            QyCons(Symbol("x"), QY_EMPTY_LIST),
        ),
    )
    result = format_value(nested)
    assert result == "(let (x 42) x)"


def test_format_value_unknown_type():
    """测试格式化未知类型使用 repr。."""

    class CustomObject:
        def __repr__(self):
            return "<CustomObject>"

    obj = CustomObject()
    result = format_value(obj)
    assert result == "<CustomObject>"
