# coding: utf-8
from __future__ import annotations

from qy.passes.pass_base import Pass
from qy.passes.pass_base import PassContext
from qy.passes.pass_base import PassResult


class LowerLIRPass(Pass):
    def __init__(self):
        super().__init__("lir.lower")

    def run(self, context: PassContext) -> PassResult:
        from typing import cast

        from qy.ir.mir import MIRProgram
        from qy.passes.lower_lir import lower_lir

        program = lower_lir(cast(MIRProgram, context.input_artifact))
        return PassResult(
            success=True,
            artifact=program,
            diagnostics=list(program.diagnostics),
        )
