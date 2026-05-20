# coding: utf-8
"""测试 qy.stdlib.modules 模块的内部函数。."""

from __future__ import annotations

import pytest

from qy.errors import QyTypeError
from qy.reader import Symbol
from qy.stdlib.modules import _is_special_form
from qy.stdlib.modules import _parse_export_names


def test_is_special_form_with_matching_form():
    """测试 _is_special_form 识别匹配的特殊形式。."""
    form = (Symbol("exports"), Symbol("x"), Symbol("y"))
    assert _is_special_form(form, "exports") is True


def test_is_special_form_with_non_matching_form():
    """测试 _is_special_form 拒绝不匹配的特殊形式。."""
    form = (Symbol("define"), Symbol("x"), 42)
    assert _is_special_form(form, "exports") is False


def test_is_special_form_with_empty_tuple():
    """测试 _is_special_form 拒绝空元组。."""
    form = ()
    assert _is_special_form(form, "exports") is False


def test_is_special_form_with_non_tuple():
    """测试 _is_special_form 拒绝非元组。."""
    form = Symbol("exports")
    assert _is_special_form(form, "exports") is False


def test_is_special_form_with_non_symbol_head():
    """测试 _is_special_form 拒绝非 Symbol 开头的元组。."""
    form = (42, Symbol("x"))
    assert _is_special_form(form, "exports") is False


def test_parse_export_names_with_symbols():
    """测试 _parse_export_names 解析符号列表。."""
    items = (Symbol("x"), Symbol("y"), Symbol("z"))
    result = _parse_export_names(items)
    assert result == [Symbol("x"), Symbol("y"), Symbol("z")]


def test_parse_export_names_with_nested_tuple():
    """测试 _parse_export_names 解析嵌套元组。."""
    items = (Symbol("x"), (Symbol("y"), Symbol("z")), Symbol("w"))
    result = _parse_export_names(items)
    assert result == [Symbol("x"), Symbol("y"), Symbol("z"), Symbol("w")]


def test_parse_export_names_with_empty_tuple():
    """测试 _parse_export_names 处理空元组。."""
    items = ()
    result = _parse_export_names(items)
    assert result == []


def test_parse_export_names_with_non_symbol_raises_error():
    """测试 _parse_export_names 拒绝非符号。."""
    items = (Symbol("x"), 42, Symbol("y"))
    with pytest.raises(QyTypeError) as exc_info:
        _parse_export_names(items)
    assert "module export" in str(exc_info.value)


def test_parse_export_names_deeply_nested():
    """测试 _parse_export_names 处理深度嵌套。."""
    items = (Symbol("a"), (Symbol("b"), (Symbol("c"), Symbol("d"))))
    result = _parse_export_names(items)
    assert result == [Symbol("a"), Symbol("b"), Symbol("c"), Symbol("d")]
