# coding: utf-8
"""MIR 阶段 pass 包。.

HIR → MIR lowering，含验证。
"""

from qy.passes.mir.normalize import lower_mir

__all__ = [
    "lower_mir",
]
