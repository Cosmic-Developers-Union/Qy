# coding: utf-8
"""``mir.validate`` pass.

校验 MIR block、register、terminator、effect flow。
"""

from __future__ import annotations

from typing import cast

from qy.ir.mir import MIRProgram
from qy.ir.mir import verify_mir
from qy.passes.pass_base import Pass
from qy.passes.pass_base import PassContext
from qy.passes.pass_base import PassResult

__all__ = ["ValidateMIRPass"]


class ValidateMIRPass(Pass):
    input_kind = "mir"
    output_kind = "mir"

    def __init__(self) -> None:
        super().__init__("mir.validate")

    def run(self, context: PassContext) -> PassResult:
        program = cast(MIRProgram, context.input_artifact)
        diagnostics = verify_mir(program)
        validated = MIRProgram(
            functions=program.functions,
            constants=program.constants,
            main=program.main,
            diagnostics=(*program.diagnostics, *diagnostics),
        )
        return PassResult(
            success=not any(d.severity == "error" for d in diagnostics),
            artifact=validated,
            artifact_kind=self.output_kind,
            diagnostics=diagnostics,
        )
