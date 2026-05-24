# coding: utf-8
"""Legacy runtime ↔ sem value 桥接层。.

迁移期工具：在 VM 完全切换到 sem value 之前，提供双向转换。
VM 直接操作 sem value 后本模块可删除。
"""

from __future__ import annotations

from qy.core.syntax import Chain
from qy.core.syntax import nil
from qy.sem.core import NIL
from qy.sem.core import ChainValue
from qy.sem.core import FloatValue
from qy.sem.core import IntValue
from qy.sem.core import NilValue
from qy.sem.core import StringValue
from qy.sem.core import T
from qy.sem.core import TValue
from qy.sem.core import Value


def to_sem(value: object) -> Value:
    """将 legacy runtime 值转为 sem Value。."""
    if value is nil or value is None:
        return NIL
    if value is T or value is True:
        return T
    if isinstance(value, Value):
        return value
    if isinstance(value, int):
        return IntValue(value)
    if isinstance(value, float):
        return FloatValue(value)
    if isinstance(value, str):
        return StringValue(value)
    if isinstance(value, Chain):
        return ChainValue(to_sem(value.head), to_sem(value.tail))
    return NIL


def from_sem(value: object) -> object:
    """将 sem Value 转回 legacy runtime 表示。."""
    if isinstance(value, NilValue):
        return nil
    if isinstance(value, TValue):
        return T
    if isinstance(value, IntValue):
        return value.value
    if isinstance(value, FloatValue):
        return value.value
    if isinstance(value, StringValue):
        return value.value
    if isinstance(value, ChainValue):
        return Chain(from_sem(value.head), from_sem(value.tail))
    return nil
