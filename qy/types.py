# coding: utf-8

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
    "symbol",
    "tuple",
    "T",
    "unknown",
]
OperatorKind = Literal["pure", "scope", "control", "effect", "meta"]
