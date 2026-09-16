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
- 完整源到字节码编译入口由 ``qy.build.pipeline`` 提供
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
    pipeline in ``qy.build.pipeline``. It only exists so IR-stage optimization
    passes can be exercised in isolation by tests and tooling.

    Optimization pipeline stages (when ``optimize=True``):

    MIR-level:
        1. const_prop  — constant propagation through MOVE/LOAD_ENV chains
        2. const_fold  — fold pure calls with constant args
        3. copy_prop   — copy propagation to eliminate redundant MOVEs
        4. dce         — dead code elimination (side-effect-free, unused results)
        5. dse         — dead store elimination (unused STORE_LOCAL/DEFINE_ONCE)
        6. cse         — common subexpression elimination
        7. strength_reduce — replace expensive pure ops with cheaper equivalents
        8. cfg_simplify — remove unreachable blocks, merge linear blocks
        9. tailcall    — detect CALL+RETURN → TAIL_CALL
       10. licm        — loop-invariant code motion
       11. loop_opt    — natural loop analysis and peeling
       12. inline      — basic single-site inlining
       13. aggressive_inline — multi-site, cross-function inlining
       14. scalar_replace — expand non-escaping tuples into scalars
       15. intern      — deduplicate constant pool entries
       16. reg_alloc   — linear scan register allocation
       17. dce         — second DCE pass (clean up after transforms)
       18. cfg_simplify — second CFG simplify (clean up after transforms)

    LIR-level (applied during lowering):
        - peephole     — MOVE r,r elimination, LOAD_NIL/LOAD_T fusion, copy forwarding
        - compact_registers — dense register renumbering
        - instr_sched  — instruction scheduling for ILP and register pressure
    """
    p = Pipeline()
    p.add_pass(LowerHIRPass())
    p.add_pass(LowerMIRPass())
    if optimize:
        from qy.passes.optimize.apply import OPTIMIZE_PASSES

        for factory in OPTIMIZE_PASSES:
            p.add_pass(factory())
    p.add_pass(LowerLIRPass())
    return p
