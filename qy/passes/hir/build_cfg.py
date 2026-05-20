# coding: utf-8
"""hir.build_cfg pass — Form → HIR lowering。.

从 S-expression forms 构建 HIR，解析符号绑定，构建作用域层次。
"""

from qy.passes.lower_hir import LoweringContext
from qy.passes.lower_hir import Scope
from qy.passes.lower_hir import lower
from qy.passes.lower_hir import lower_source

__all__ = [
    "LoweringContext",
    "Scope",
    "lower",
    "lower_source",
]
