# coding: utf-8
"""LIR 阶段 pass 包。.

MIR → LIR lowering，含验证和规范化。
"""

from qy.passes.lir.lower import _peephole
from qy.passes.lir.lower import lower_lir

__all__ = [
    "_peephole",
    "lower_lir",
]
