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
from qy.passes.hir.lower_pass import LowerHIRPass
from qy.passes.lir.lower import lower_lir
from qy.passes.lir.lower_pass import LowerLIRPass
from qy.passes.mir.lower_pass import LowerMIRPass
from qy.passes.mir.normalize import lower_mir

# Pass 基础设施
from qy.passes.pass_base import Pass
from qy.passes.pass_base import PassContext
from qy.passes.pass_base import PassResult
from qy.passes.pipeline import Pipeline

__all__ = [
    # Pass 类
    "LowerHIRPass",
    "LowerLIRPass",
    "LowerMIRPass",
    # 现有 lowering 函数
    "LoweringContext",
    # Pass 基础设施
    "Pass",
    "PassContext",
    "PassResult",
    "Pipeline",
    "Scope",
    "create_pipeline",
    "lower",
    "lower_lir",
    "lower_mir",
    "lower_source",
]


def create_pipeline(optimize: bool = False) -> Pipeline:
    p = Pipeline()
    p.add_pass(LowerHIRPass())
    p.add_pass(LowerMIRPass())
    if optimize:
        from qy.passes.control.cfg_simplify import CFGSimplifyPass
        from qy.passes.control.tailcall import TailCallPass
        from qy.passes.optimize.const_fold import ConstFoldPass
        from qy.passes.optimize.dce import DCEPass
        from qy.passes.optimize.inline import InlinePass

        p.add_pass(ConstFoldPass())
        p.add_pass(DCEPass())
        p.add_pass(CFGSimplifyPass())
        p.add_pass(TailCallPass())
        p.add_pass(InlinePass())
        p.add_pass(DCEPass())
        p.add_pass(CFGSimplifyPass())
    p.add_pass(LowerLIRPass())
    return p
