# coding: utf-8
"""MIR 优化序列与其在默认管线中的接线点。.

``OPTIMIZE_PASSES`` 是优化 pass 的唯一顺序真源，供两处使用：

- ``qy.passes.build_optimization_pipeline``（隔离测试用的 HIR→MIR→LIR 子管线）；
- ``OptimizeMIRPass``（默认管线中 ``mir.validate`` 之后的接线点）。

``OptimizeMIRPass`` 默认是 no-op：只有 ``PipelineOptions.optimize`` 为真时才运行
优化序列。是否默认开启由优化 pass 对 language-level effect / continuation 控制流
的正确性决定（见 todo.md §Phase P）。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import cast

from qy.diag import Diagnostic
from qy.ir.mir import MIRProgram
from qy.passes.pass_base import Pass
from qy.passes.pass_base import PassContext
from qy.passes.pass_base import PassResult

__all__ = ["OPTIMIZE_PASSES", "OptimizeMIRPass", "optimize_mir"]


def _pass_factories():
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

    # Phase 1: 简化
    yield ConstPropagationPass
    yield ConstFoldPass
    yield CopyPropagationPass
    yield DCEPass
    yield DeadStoreEliminationPass
    # Phase 2: 代数化简
    yield CSEPass
    yield StrengthReducePass
    yield CFGSimplifyPass
    # Phase 3: 控制流
    yield TailCallPass
    yield LICMPass
    yield LoopOptPass
    # Phase 4: 内联
    yield InlinePass
    yield AggressiveInlinePass
    # Phase 5: 清理与准备
    yield ScalarReplacePass
    yield InternPass
    yield DCEPass
    yield CFGSimplifyPass
    # Phase 6: 寄存器分配
    yield RegisterAllocationPass


#: 优化 pass 的顺序真源（每个元素是无参 ``Pass`` 工厂）。
OPTIMIZE_PASSES: tuple[Callable[[], Pass], ...] = tuple(_pass_factories())


def optimize_mir(
    program: MIRProgram, context: PassContext
) -> tuple[MIRProgram, tuple[Diagnostic, ...]]:
    """按 ``OPTIMIZE_PASSES`` 顺序优化 *program*，返回 (program, diagnostics)。."""
    artifact: object = program
    diagnostics: list[Diagnostic] = []
    for factory in OPTIMIZE_PASSES:
        pass_context = PassContext(
            input_artifact=artifact,
            artifact_kind="mir",
            session=context.session,
            diagnostics=(),
            options=context.options,
        )
        result = cast(PassResult, factory().run(pass_context))
        diagnostics.extend(result.diagnostics)
        artifact = result.artifact
    return cast(MIRProgram, artifact), tuple(diagnostics)


class OptimizeMIRPass(Pass):
    """按需运行 MIR 优化序列；``PipelineOptions.optimize`` 为假时是 no-op。."""

    input_kind = "mir"
    output_kind = "mir"

    def __init__(self) -> None:
        super().__init__("optimize.mir")

    def run(self, context: PassContext) -> PassResult:
        program = cast(MIRProgram, context.input_artifact)
        if not context.options.optimize:
            return PassResult(success=True, artifact=program, artifact_kind=self.output_kind)
        optimized, diagnostics = optimize_mir(program, context)
        has_errors = any(diagnostic.severity == "error" for diagnostic in diagnostics)
        return PassResult(
            success=not has_errors,
            artifact=optimized,
            artifact_kind=self.output_kind,
            diagnostics=diagnostics,
        )
