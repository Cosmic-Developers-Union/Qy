# coding: utf-8
"""宿主值与 Qy 语义值之间的转换（单一实现）。.

这是**宿主对象边界**的唯一转换实现：扩展（``qy.ext.*``）与嵌入式宿主都用它，
不得各自维护一份。转换规则：

宿主 → Qy（:func:`to_qy_value`）：

- ``nil`` / ``T`` / ``Chain`` / ``HostReference`` / ``Symbol`` 原样传入；
- ``None`` → ``none``；``bool`` / ``int`` / ``float`` 保持宿主原生数（本项目在
  边界上不强制包装成 ``IntValue``）；``str`` → ``StringValue``；
- ``list`` / ``tuple`` / ``dict`` / ``set`` → ``ListValue`` / ``TupleValue`` /
  ``DictValue`` / ``SetValue``（递归）；
- 其余对象 → :class:`qy.sem.host.HostReference`（不透明包装）。

Qy → 宿主（:func:`from_qy_value`）：

- ``HostReference`` 解包为其宿主对象；
- 数值 / 字符串 / 字符值解包为宿主 ``int``/``float``/``str``；
- 容器值递归解包为宿主 ``list`` / ``dict``；
- ``nil`` / ``T`` / ``none``、函数值、算子、effect 定义等语言级值**保持原样**
  （它们没有忠实的宿主对应物，解包会丢语义）。

禁止：
- 不得在语言内核里自动调用这些转换（内核只见 Qy 语义值）；
- 不得在这里做 capability / 权限判断（那是 ``qy.ext.ExtensionPolicy`` 的职责）。
"""

from __future__ import annotations

from qy.core.syntax import NONE as QY_NONE
from qy.core.syntax import Chain
from qy.core.syntax import T as QY_T
from qy.core.syntax import map_chain
from qy.core.syntax import nil as QY_NIL
from qy.sem.core import CharValue
from qy.sem.core import DictValue
from qy.sem.core import Float32Value
from qy.sem.core import FloatValue
from qy.sem.core import HashMapValue
from qy.sem.core import Int32Value
from qy.sem.core import Int64Value
from qy.sem.core import IntValue
from qy.sem.core import ListValue
from qy.sem.core import SetValue
from qy.sem.core import StringValue
from qy.sem.core import TupleValue
from qy.sem.host import HostReference

__all__ = ["from_qy_value", "to_qy_value"]

#: 解包成宿主数字的值类型。
_NUMBER_VALUES = (IntValue, FloatValue, Int32Value, Int64Value, Float32Value)

#: 解包成宿主字符串的值类型。
_TEXT_VALUES = (StringValue, CharValue)

#: 解包成宿主标量（数字 / 字符串 / 字符）的值类型。
_UNWRAP_VALUES = (*_NUMBER_VALUES, *_TEXT_VALUES)


def to_qy_value(value: object) -> object:
    """把宿主值转换成 Qy 语义值（未知对象包装为 HostReference）。."""
    from qy.core.syntax import Symbol

    if value is QY_NIL or value is QY_T:
        return value
    if isinstance(value, Chain):
        return map_chain(value, to_qy_value)
    if isinstance(value, HostReference | Symbol):
        return value
    if value is None:
        return QY_NONE
    if isinstance(value, bool | int | float):
        return value
    if isinstance(value, str):
        return StringValue(value)
    if isinstance(value, list):
        return ListValue(tuple(to_qy_value(item) for item in value))
    if isinstance(value, tuple):
        return TupleValue(tuple(to_qy_value(item) for item in value))
    if isinstance(value, dict):
        return DictValue(
            tuple((to_qy_value(key), to_qy_value(item)) for key, item in value.items())
        )
    if isinstance(value, set):
        return SetValue(tuple(to_qy_value(item) for item in value))
    return HostReference(value)


def from_qy_value(value: object) -> object:
    """把 Qy 语义值解包成宿主值；没有宿主对应物的语言级值原样返回。."""
    if isinstance(value, HostReference):
        return value.value
    if isinstance(value, _UNWRAP_VALUES):
        return value.value
    if isinstance(value, TupleValue | ListValue | SetValue):
        return [from_qy_value(item) for item in value.items]
    if isinstance(value, DictValue | HashMapValue):
        return {
            from_qy_value(key): from_qy_value(item) for key, item in value.entries
        }
    return value
