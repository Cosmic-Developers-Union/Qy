# coding: utf-8
from __future__ import annotations

from qy.passes.pass_base import Pass
from qy.passes.pass_base import PassContext
from qy.passes.pass_base import PassResult


class LowerMIRPass(Pass):
    def __init__(self):
        super().__init__("mir.lower")

    def run(self, context: PassContext) -> PassResult:
        from typing import cast

        from qy.ir.hir.node import ProgramIR
        from qy.passes.lower_mir import lower_mir

        program = lower_mir(cast(ProgramIR, context.input_artifact))
        return PassResult(
            success=True,
            artifact=program,
            diagnostics=list(program.diagnostics),
        )
