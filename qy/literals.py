# coding: utf-8

from __future__ import annotations

from qy.errors import QyResolveError
from qy.reader import Symbol
from qy.types import TypeName
from qy.values import QY_NIL
from qy.values import QY_T

__all__ = [
    "default_literal_type",
    "resolve_default_literal",
    "try_default_literal",
]

_MISSING = object()


def try_default_literal(symbol: Symbol) -> object:
    if symbol.name == "T":
        return QY_T
    if symbol.name == "nil":
        return QY_NIL
    if symbol.name == "true":
        return QY_T
    if symbol.name == "false":
        return QY_NIL
    if symbol.name == "none":
        return None
    try:
        return int(symbol.name)
    except ValueError:
        pass
    try:
        return float(symbol.name)
    except ValueError:
        pass
    return _MISSING


def resolve_default_literal(symbol: Symbol) -> object:
    value = try_default_literal(symbol)
    if value is not _MISSING:
        return value
    raise QyResolveError(
        f"unresolved symbol {symbol.name!r}",
        span=symbol.span,
        metadata={"symbol": symbol.name},
    )


def default_literal_type(symbol: Symbol) -> TypeName | None:
    value = try_default_literal(symbol)
    if value is _MISSING:
        return None
    if value is QY_NIL:
        return "nil"
    if value is QY_T:
        return "T"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int | float):
        return "number"
    if value is None:
        return "none"
