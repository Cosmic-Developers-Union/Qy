# coding: utf-8
"""测试 qy.symbol_utils 模块。."""

from __future__ import annotations

import pytest

from qy.errors import QyTypeError
from qy.reader import Symbol
from qy.symbol_utils import ensure_symbol


def test_ensure_symbol_with_symbol():
    """测试 ensure_symbol 接受 Symbol。."""
    sym = Symbol("test")
    result = ensure_symbol(sym, "test context")
    assert result is sym


def test_ensure_symbol_with_non_symbol():
    """测试 ensure_symbol 拒绝非 Symbol。."""
    with pytest.raises(QyTypeError) as exc_info:
        ensure_symbol("not-a-symbol", "test context")

    assert "test context" in str(exc_info.value)
    assert "must be a symbol" in str(exc_info.value)


def test_ensure_symbol_with_int():
    """测试 ensure_symbol 拒绝整数。."""
    with pytest.raises(QyTypeError) as exc_info:
        ensure_symbol(42, "parameter")

    assert "parameter" in str(exc_info.value)
    assert "must be a symbol" in str(exc_info.value)


def test_ensure_symbol_with_none():
    """测试 ensure_symbol 拒绝 None。."""
    with pytest.raises(QyTypeError):
        ensure_symbol(None, "value")


def test_ensure_symbol_error_metadata():
    """测试 ensure_symbol 错误包含元数据。."""
    with pytest.raises(QyTypeError) as exc_info:
        ensure_symbol(123, "test-context")

    error = exc_info.value
    assert error.metadata is not None
    assert error.metadata.get("context") == "test-context"
    assert error.metadata.get("value") == 123
