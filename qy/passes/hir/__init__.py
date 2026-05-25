# coding: utf-8
"""HIR 阶段 pass 包。.

Form → HIR lowering，含验证。
"""

from qy.passes.hir.lower_pass import LowerHIRPass

__all__ = [
    "LowerHIRPass",
]
