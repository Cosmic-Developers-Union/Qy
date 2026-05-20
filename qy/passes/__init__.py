# coding: utf-8
"""Pass 系统：staged transforms and analyses。.

目标：
- 按"阶段 + 主题"组织所有 pass
- 支持 --after / --target dump
- 提供统一 Pass 基类和调度器

禁止：
- pass 不得定义 IR 数据结构（那是 qy/ir/ 的职责）
- pass 不得直接执行（那是 qy/build/ 的职责）
"""

from __future__ import annotations

# 新子目录路径 —— 这些是正式导入来源
from qy.passes.hir.build_cfg import LoweringContext
from qy.passes.hir.build_cfg import Scope
from qy.passes.hir.build_cfg import lower
from qy.passes.hir.build_cfg import lower_source
from qy.passes.lir.lower import lower_lir
from qy.passes.mir.normalize import lower_mir

# Pass 基础设施
from qy.passes.pass_base import Pass
from qy.passes.pass_base import PassContext
from qy.passes.pass_base import PassResult
from qy.passes.pipeline import Pipeline

__all__ = [
    # 现有 lowering passes
    "LoweringContext",
    # Pass 基础设施
    "Pass",
    "PassContext",
    "PassResult",
    "Pipeline",
    "Scope",
    "lower",
    "lower_hir",
    "lower_lir",
    "lower_mir",
    "lower_source",
]
