# coding: utf-8

from __future__ import annotations

from qy.core.syntax import Chain
from qy.core.syntax import Symbol
from qy.core.syntax import T
from qy.core.syntax import nil
from qy.frontend.reader import write

__all__ = ["format_value"]


def format_value(value: object) -> str:
    from qy.core.syntax import NONE
    from qy.core.syntax import NoneValue
    from qy.sem.core import DictValue
    from qy.sem.core import ListValue
    from qy.sem.core import NumberValue
    from qy.sem.core import SetValue
    from qy.sem.core import StringValue
    from qy.sem.core import TupleValue

    if value is nil:
        return "nil"
    if value is T:
        return "T"
    if value is NONE or isinstance(value, NoneValue):
        return "none"
    if isinstance(value, NumberValue):
        return str(value)
    if isinstance(value, StringValue):
        return value.value
    if isinstance(value, Chain):
        return _format_cons(value)
    if isinstance(value, Chain):
        return _format_cons(value)
    if isinstance(value, str):
        return value
    if isinstance(value, TupleValue):
        return f"({' '.join(format_value(item) for item in value.items)})"
    if isinstance(value, ListValue):
        return f"[{' '.join(format_value(item) for item in value.items)}]"
    if isinstance(value, DictValue):
        items = [f"{format_value(key)} {format_value(item)}" for key, item in value.entries]
        return f"{{{' '.join(items)}}}"
    if isinstance(value, SetValue):
        items = sorted(format_value(item) for item in value.items)
        return f"#{{{' '.join(items)}}}"
    if isinstance(value, tuple):
        return f"({' '.join(format_value(item) for item in value)})"
    if isinstance(value, Symbol):
        return write(value)
    if value is True:
        return "true"
    if value is False:
        return "false"
    if value is None:
        return "none"
    if isinstance(value, int | float):
        return repr(value)
    if isinstance(value, list):
        return f"[{' '.join(format_value(item) for item in value)}]"
    if isinstance(value, dict):
        items = [f"{format_value(key)} {format_value(item)}" for key, item in value.items()]
        return f"{{{' '.join(items)}}}"
    if isinstance(value, set):
        items = sorted(format_value(item) for item in value)
        return f"#{{{' '.join(items)}}}"
    return repr(value)


def _format_cons(value: Chain) -> str:
    parts: list[str] = []
    current: object = value
    while isinstance(current, Chain):
        parts.append(format_value(current.head))
        current = current.tail
    if current is nil:
        return f"({' '.join(parts)})"
    return f"({' '.join(parts)} . {format_value(current)})"
