# coding: utf-8
"""测试 qy.sem.bridge 模块的边界情况。."""

from __future__ import annotations

from qy.core.syntax import nil as QY_NIL
from qy.sem.bridge import from_sem
from qy.sem.core import NilValue


def test_from_sem_nil_value():
    """测试从 NilValue 转换。."""
    result = from_sem(NilValue())
    assert result is QY_NIL


def test_from_sem_unknown_value():
    """测试从未知类型转换返回 NIL。."""

    class UnknownValue:
        pass

    result = from_sem(UnknownValue())
    assert result is QY_NIL
