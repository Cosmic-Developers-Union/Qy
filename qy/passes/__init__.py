# coding: utf-8
"""Compiler passes.

Public API:
    from qy.passes import lower_hir, lower_mir, lower_lir
"""

from __future__ import annotations

from qy.passes.lower_hir import (
    LoweringContext,
    Scope,
    lower,
    lower_source,
)

from qy.passes.lower_mir import (
    lower_mir,
)

from qy.passes.lower_lir import (
    lower_lir,
)

__all__ = [
    "LoweringContext",
    "Scope",
    "lower",
    "lower_hir",
    "lower_mir",
    "lower_lir",
    "lower_source",
]