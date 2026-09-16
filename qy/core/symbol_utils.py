# coding: utf-8

from __future__ import annotations

from qy.core.syntax import Symbol
from qy.core.syntax import get_span
from qy.errors import QyTypeError

__all__ = ["ensure_symbol"]


def ensure_symbol(value: object, context: str) -> Symbol:
    if not isinstance(value, Symbol):
        raise QyTypeError(
            f"{context} must be a symbol, got {value!r}",
            span=get_span(value),
            metadata={"context": context, "value": value},
        )
    return value
