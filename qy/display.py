# coding: utf-8

from __future__ import annotations

from typing import cast

from qy.core.syntax import Chain
from qy.core.syntax import is_chain
from qy.core.syntax import nil
from qy.frontend.reader import Symbol
from qy.frontend.reader import TupleForm
from qy.frontend.reader import write_tuple
from qy.sem.core import T

__all__ = ["format_value"]


def format_value(value: object) -> str:
    if value is nil:
        return "nil"
    if value is T:
        return "T"
    if isinstance(value, Chain):
        return _format_cons(value)
    # Handle AST Chain
    if isinstance(value, Chain) or is_chain(value):
        return _format_chain(value)
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


def _format_cons(value: Chain) -> str:
    parts: list[str] = []
    current: object = value
    while isinstance(current, Chain):
        parts.append(format_value(current.head))
        current = current.tail
    if current is nil:
        return f"({' '.join(parts)})"
    return f"({' '.join(parts)} . {format_value(current)})"


def _format_chain(value: object) -> str:
    from qy.core.syntax import car
    from qy.core.syntax import cdr
    from qy.core.syntax import is_chain
    from qy.core.syntax import is_nil

    parts: list[str] = []
    current: object = value
    while is_chain(current):
        parts.append(format_value(car(current)))
        current = cdr(current)
    if is_nil(current):
        return f"({' '.join(parts)})"
    return f"({' '.join(parts)} . {format_value(current)})"
