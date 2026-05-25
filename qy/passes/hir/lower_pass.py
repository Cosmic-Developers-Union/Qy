# coding: utf-8
from __future__ import annotations

from qy.passes.pass_base import Pass
from qy.passes.pass_base import PassContext
from qy.passes.pass_base import PassResult


class LowerHIRPass(Pass):
    def __init__(self):
        super().__init__("hir.lower")

    def run(self, context: PassContext) -> PassResult:
        from qy.passes.lower_hir import lower

        forms = context.input_artifact
        env = context.options.get("env")
        program = lower(forms, env)
        return PassResult(
            success=True,
            artifact=program,
            diagnostics=list(program.diagnostics),
        )
