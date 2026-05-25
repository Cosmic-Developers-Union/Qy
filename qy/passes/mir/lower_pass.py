# coding: utf-8
from __future__ import annotations

from typing import cast

from qy.ir.hir.node import ProgramIR
from qy.passes.lower_mir import lower_mir
from qy.passes.pass_base import Pass
from qy.passes.pass_base import PassContext
from qy.passes.pass_base import PassResult


class LowerMIRPass(Pass):
    input_kind = "hir"
    output_kind = "mir"

    def __init__(self) -> None:
        super().__init__("mir.lower")

    def run(self, context: PassContext) -> PassResult:
        hir = cast(ProgramIR, context.input_artifact)
        program = lower_mir(hir)
        # ``lower_mir`` 把上游 HIR 的诊断也复制到 ``MIRProgram.diagnostics``。
        # 上游诊断由 Pipeline 自身累计，这里只回报本 pass 新产生的部分。
        upstream_ids = {id(d) for d in hir.diagnostics}
        new_diagnostics = tuple(d for d in program.diagnostics if id(d) not in upstream_ids)
        return PassResult(
            success=True,
            artifact=program,
            artifact_kind=self.output_kind,
            diagnostics=new_diagnostics,
        )
