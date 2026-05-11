# coding: utf-8

from __future__ import annotations

from typing import cast

from qy.reader import Symbol
from qy.reader import TupleForm
from qy.reader import write_tuple

__all__ = ["format_value"]


def format_value(value: object) -> str:
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
