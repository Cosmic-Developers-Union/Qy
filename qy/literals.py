# coding: utf-8
# QY_DELETE_AFTER_SEMANTIC_REPLACEMENT: target=pre-symbol-space-chain literal layer
#
# DEPRECATED: This module is being replaced by qy/session/pre_ss.py
#
# Migration status:
# - New implementation: qy/session/pre_ss.py (pre-symbol-space architecture)
# - ProfileConfig updated to use pre-ss by default (use_pre_ss=True)
# - Legacy mode available via ProfileConfig(use_pre_ss=False)
# - All tests passing with new implementation
#
# This module remains for backward compatibility and will be removed once
# all references are migrated to the pre-symbol-space architecture.

from __future__ import annotations

from qy.core import TypeName
from qy.errors import QyResolveError
from qy.reader import Symbol
from qy.values import QY_NIL
from qy.values import QY_T

__all__ = [
    "default_literal_type",
    "resolve_default_literal",
    "try_default_literal",
]

_MISSING = object()


def _is_string_literal(name: str) -> bool:
    return name.startswith('"') or name.startswith('r"')


def _decode_string_literal(name: str) -> object:
    import ast

    try:
        value = ast.literal_eval(name)
    except (SyntaxError, ValueError):
        return _MISSING
    if not isinstance(value, str):
        return _MISSING
    return value


def try_default_literal(symbol: Symbol) -> object:
    if _is_string_literal(symbol.name):
        return _decode_string_literal(symbol.name)
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
    if _is_string_literal(symbol.name):
        return "string"
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
