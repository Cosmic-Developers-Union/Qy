# coding: utf-8
"""后端共享的常量分类。.

LIR 的 ``LOAD_HOST`` 携带的是 **Qy 值**（``IntValue`` / ``StringValue`` /
``CharValue`` / ``T`` / ``nil`` / ``none``），也可能携带宿主 Python 标量。
各后端 ABI 不同（wasm 用 tagged i64，llvm 用 ``%qy_value`` 结构 + tag），但
「这是什么常量」的判断必须只有一份，否则后端会各自漏掉类型并静默产出错误值
（历史缺陷：两个后端都把 ``IntValue`` 落成 nil）。

本模块只做分类，不做编码；编码由各后端按自己的 ABI 完成。
"""

from __future__ import annotations

from qy.core.syntax import NONE
from qy.core.syntax import Chain
from qy.core.syntax import Symbol
from qy.core.syntax import T as QY_T
from qy.sem.core import CharValue
from qy.sem.core import IntValue
from qy.sem.core import NumberValue
from qy.sem.core import StringValue

__all__ = ["Constant", "classify_constant"]

#: 分类结果：``(kind, payload)``。
#: kind ∈ {"nil", "none", "t", "bool", "int", "float", "string", "char", "symbol", "chain", "host"}
Constant = tuple[str, object]


def classify_constant(value: object) -> Constant:
    """把 Qy 值 / 宿主标量分类成后端可映射的常量。."""
    if value is None:
        return ("nil", None)
    if isinstance(value, bool):
        return ("bool", value)
    if isinstance(value, IntValue):
        return ("int", value.value)
    if isinstance(value, NumberValue):
        return ("float", value.value)
    if isinstance(value, StringValue):
        return ("string", value.value)
    if isinstance(value, CharValue):
        return ("char", value.value)
    if isinstance(value, int):
        return ("int", value)
    if isinstance(value, float):
        return ("float", value)
    if isinstance(value, str):
        return ("string", value)
    if value is QY_T:
        return ("t", None)
    if value is NONE:
        return ("none", None)
    if _is_nil(value):
        return ("nil", None)
    if isinstance(value, Symbol):
        return ("symbol", value)
    if isinstance(value, Chain):
        return ("chain", value)
    return ("host", value)


def _is_nil(value: object) -> bool:
    from qy.core.syntax import QyNil

    return isinstance(value, QyNil)
