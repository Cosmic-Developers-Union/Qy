# coding: utf-8

from __future__ import annotations

from typing import cast

from qy.reader import Symbol
from qy.reader import TupleForm
from qy.reader import write_tuple
from qy.values import QY_EMPTY_LIST
from qy.values import QY_NIL
from qy.values import QY_T
from qy.values import QyCons

__all__ = ["format_value"]


def format_value(value: object) -> str:
    if value is QY_NIL:
        return "nil"
    if value is QY_T:
        return "T"
    if isinstance(value, QyCons):
        return _format_cons(value)
    if isinstance(value, str):
        return value
    if isinstance(value, Symbol | tuple | int | float | bool) or value is None:
        try:
            return write_tuple(cast(TupleForm, value))
        except TypeError:
            pass
    if isinstance(value, list):
        return f"[{' '.join(format_value(item) for item in value)}]"
    if isinstance(value, dict):
        items = [f"{format_value(key)} {format_value(item)}" for key, item in value.items()]
        return f"{{{' '.join(items)}}}"
    if isinstance(value, set):
        items = sorted(format_value(item) for item in value)
        return f"#{{{' '.join(items)}}}"
    return repr(value)


def _format_cons(value: QyCons) -> str:
    parts: list[str] = []
    current: object = value
    while isinstance(current, QyCons):
        parts.append(format_value(current.head))
        current = current.tail
    if current is QY_EMPTY_LIST:
        return f"({' '.join(parts)})"
    return f"({' '.join(parts)} . {format_value(current)})"
