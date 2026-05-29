# coding: utf-8
from __future__ import annotations

from collections.abc import Iterable
from typing import cast

from qy.core.program import CoreProgram
from qy.frontend.form import Form
from qy.passes.hir.lower import lower
from qy.passes.pass_base import Pass
from qy.passes.pass_base import PassContext
from qy.passes.pass_base import PassResult


class LowerHIRPass(Pass):
    input_kind = "core-ast"
    output_kind = "hir"

    def __init__(self) -> None:
        super().__init__("hir.lower")

    def run(self, context: PassContext) -> PassResult:
        artifact = context.input_artifact
        forms: list[Form]
        if isinstance(artifact, CoreProgram):
            forms = list(artifact.forms)
        else:
            forms = list(cast(Iterable[Form], artifact))
        program = lower(forms, context.session.env)
        # ProgramIR.diagnostics 仅由 hir.lower 自身产生（上游诊断由 Pipeline 累计），
        # 因此可以直接整体上报。
        return PassResult(
            success=True,
            artifact=program,
            artifact_kind=self.output_kind,
            diagnostics=tuple(program.diagnostics),
        )
