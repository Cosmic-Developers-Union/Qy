# coding: utf-8
"""Operator type declarations — canonical source for TypeName / OperatorKind.

This private module (with leading underscore) holds the actual type definitions so
that both qy/types.py (backward compat) and qy/core/__init__.py (new canonical
source) can import from here without triggering circular import of the qy package.
"""
# QY_DELETE_AFTER_MIGRATION: target=qy/core/__init__.py
# All types should be defined in qy/core/__init__.py directly.
# This file exists only to break the circular import: qy.types -> qy.core -> qy.

from __future__ import annotations

__all__ = ["OperatorKind", "TypeName"]  # noqa: F822


# Re-export from qy/core/__init__.py for backward compatibility.
# Use __getattr__ to lazily import typing.Literal — avoids triggering
# Python stdlib `types` shadow at load time (qy/types.py shadows stdlib types).
def __getattr__(name: str):
    if name == "OperatorKind":
        from qy.core import OperatorKind

        return OperatorKind
    if name == "TypeName":
        from qy.core import TypeName

        return TypeName
    raise AttributeError(name)
