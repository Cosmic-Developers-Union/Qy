# coding: utf-8
# QY_DELETE_AFTER_MIGRATION: target=qy/core/* or qy/sem/*

from __future__ import annotations

from typing import Literal

__all__ = ["OperatorKind", "TypeName"]

TypeName = Literal[
    "any",
    "bool",
    "chain",
    "dict",
    "effect",
    "function",
    "list",
    "nil",
    "none",
    "number",
    "operator",
    "set",
    "string",
    "symbol",
    "tuple",
    "T",
    "unknown",
]
OperatorKind = Literal["pure", "scope", "control", "effect", "meta"]
