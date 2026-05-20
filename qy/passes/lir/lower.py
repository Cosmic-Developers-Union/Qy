# coding: utf-8
"""lir.lower pass — MIR → LIR lowering。.

将 MIR 降到 LIR abstract machine IR，含 instruction selection、layout、ABI、
virtual stack、continuation frame、peephole。
"""

from qy.passes.lower_lir import _peephole
from qy.passes.lower_lir import lower_lir

__all__ = [
    "_peephole",
    "lower_lir",
]
