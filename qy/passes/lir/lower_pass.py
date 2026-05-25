# coding: utf-8
from __future__ import annotations

from typing import cast

from qy.ir.mir import MIRProgram
from qy.passes.lir.lower import lower_lir
from qy.passes.pass_base import Pass
from qy.passes.pass_base import PassContext
from qy.passes.pass_base import PassResult


class LowerLIRPass(Pass):
    input_kind = "mir"
    output_kind = "lir"

    def __init__(self) -> None:
        super().__init__("lir.lower")

    def run(self, context: PassContext) -> PassResult:
        mir = cast(MIRProgram, context.input_artifact)
        program = lower_lir(mir)
        upstream_ids = {id(d) for d in mir.diagnostics}
        new_diagnostics = tuple(d for d in program.diagnostics if id(d) not in upstream_ids)
        return PassResult(
            success=True,
            artifact=program,
            artifact_kind=self.output_kind,
            diagnostics=new_diagnostics,
        )
