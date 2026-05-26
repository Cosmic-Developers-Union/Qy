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
        from qy.passes.control.cfg_simplify import CFGSimplifyPass
        from qy.passes.control.loop_opt import LoopOptPass
        from qy.passes.control.tailcall import TailCallPass
        from qy.passes.optimize.aggressive_inline import AggressiveInlinePass
        from qy.passes.optimize.const_fold import ConstFoldPass
        from qy.passes.optimize.const_prop import ConstPropagationPass
        from qy.passes.optimize.copy_prop import CopyPropagationPass
        from qy.passes.optimize.cse import CSEPass
        from qy.passes.optimize.dce import DCEPass
        from qy.passes.optimize.dse import DeadStoreEliminationPass
        from qy.passes.optimize.inline import InlinePass
        from qy.passes.optimize.intern import InternPass
        from qy.passes.optimize.licm import LICMPass
        from qy.passes.optimize.reg_alloc import RegisterAllocationPass
        from qy.passes.optimize.scalar_replace import ScalarReplacePass
        from qy.passes.optimize.strength_reduce import StrengthReducePass

        # Phase 1: Simplification
        p.add_pass(ConstPropagationPass())
        p.add_pass(ConstFoldPass())
        p.add_pass(CopyPropagationPass())
        p.add_pass(DCEPass())
        p.add_pass(DeadStoreEliminationPass())

        # Phase 2: Algebraic simplification
        p.add_pass(CSEPass())
        p.add_pass(StrengthReducePass())
        p.add_pass(CFGSimplifyPass())

        # Phase 3: Control flow optimization
        p.add_pass(TailCallPass())
        p.add_pass(LICMPass())
        p.add_pass(LoopOptPass())

        # Phase 4: Inlining
        p.add_pass(InlinePass())
        p.add_pass(AggressiveInlinePass())

        # Phase 5: Cleanup and preparation
        p.add_pass(ScalarReplacePass())
        p.add_pass(InternPass())
        p.add_pass(DCEPass())
        p.add_pass(CFGSimplifyPass())

        # Phase 6: Register allocation
        p.add_pass(RegisterAllocationPass())
    p.add_pass(LowerLIRPass())
    return p
