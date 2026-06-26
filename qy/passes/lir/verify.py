# coding: utf-8
"""``lir.verify`` pass.

校验 LIR 的 frame、handler、continuation、slot、lookup、branch、debug metadata。
LIR 可验证性是 VM backend 与 LLVM backend 共用可靠输入的前提。
"""

from __future__ import annotations

from typing import cast

from qy.ir.lir import LIRProgram
from qy.ir.lir import verify_lir
from qy.passes.pass_base import Pass
from qy.passes.pass_base import PassContext
from qy.passes.pass_base import PassResult

__all__ = ["VerifyLIRPass"]


class VerifyLIRPass(Pass):
    input_kind = "lir"
    output_kind = "lir"

    def __init__(self) -> None:
        super().__init__("lir.verify")

    def run(self, context: PassContext) -> PassResult:
        program = cast(LIRProgram, context.input_artifact)
        diagnostics = verify_lir(program)
        verified = LIRProgram(
            program.functions,
            program.main,
            (*program.diagnostics, *diagnostics),
            program.dialect,
        )
        return PassResult(
            success=not any(d.severity == "error" for d in diagnostics),
            artifact=verified,
            artifact_kind=self.output_kind,
            diagnostics=diagnostics,
        )
