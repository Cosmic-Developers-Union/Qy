# coding: utf-8
"""Pass 系统：staged transforms and analyses。.

目标：
- 按"阶段 + 主题"组织所有 pass
- 支持 --after / --target dump
- 提供统一 Pass 基类和调度器

禁止：
- pass 不得定义 IR 数据结构（那是 qy/ir/ 的职责）
- pass 不得直接执行（那是 qy/build/ 的职责）

注意：
- 完整源到字节码编译入口由 ``qy.passes.build`` 提供
  （``build_default_pipeline``、``compile_source_to_*``、
  ``compile_source_to_kind*``）。
- 这里仅暴露 pass 类与调度基础设施，以及 IR 阶段优化测试用的
  ``build_optimization_pipeline`` 子流水线。
- 不再提供绕过 pipeline 的 ``lower``/``lower_mir``/``lower_lir`` 等单段函数。
"""

from __future__ import annotations

from qy.passes.hir.lower_pass import LowerHIRPass
from qy.passes.lir.lower_pass import LowerLIRPass
from qy.passes.mir.lower_pass import LowerMIRPass
from qy.passes.pass_base import Pass
from qy.passes.pass_base import PassContext
from qy.passes.pass_base import PassResult
from qy.passes.pipeline import Pipeline

__all__ = [
    "LowerHIRPass",
    "LowerLIRPass",
    "LowerMIRPass",
    "Pass",
    "PassContext",
    "PassResult",
    "Pipeline",
    "build_optimization_pipeline",
]


def build_optimization_pipeline(*, optimize: bool = False) -> Pipeline:
    """Build a HIR→MIR→(optionally optimized)→LIR sub-pipeline.

    This sub-pipeline is **not** a substitute for the canonical source→bytecode
    pipeline in ``qy.passes.build``. It only exists so IR-stage optimization
    passes (const-fold, DCE, CFG simplify, tail-call, inline) can be exercised
    in isolation by tests and tooling.
    """
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
