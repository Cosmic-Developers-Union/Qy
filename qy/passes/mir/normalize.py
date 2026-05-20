# coding: utf-8
"""mir.normalize pass — HIR → MIR lowering。.

将 HIR 降为 MIR CFG / virtual register IR。
"""

from qy.passes.lower_mir import lower_mir

__all__ = [
    "lower_mir",
]
