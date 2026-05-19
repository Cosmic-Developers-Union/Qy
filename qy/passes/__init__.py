# coding: utf-8
"""Qy compiler passes.

目标：
- `lower_hir`: macro-expanded forms -> HIR。
- `lower_mir`: HIR -> MIR。
- `lower_lir`: MIR -> LIR。

约束：
- passes 可以 import IR model；IR model 不得反向 import passes。
- bytecode emit 不属于 passes，应位于 `qy/vm`。
"""

from __future__ import annotations

from qy.passes.lower_hir import LoweringContext
from qy.passes.lower_hir import Scope
from qy.passes.lower_hir import lower
from qy.passes.lower_hir import lower_source
from qy.passes.lower_lir import lower_lir
from qy.passes.lower_mir import lower_mir

__all__ = [
    "LoweringContext",
    "Scope",
    "lower",
    "lower_hir",
    "lower_lir",
    "lower_mir",
    "lower_source",
]
