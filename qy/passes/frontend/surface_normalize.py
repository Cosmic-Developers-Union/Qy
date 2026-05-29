# coding: utf-8
"""``frontend.surface_normalize`` —— raw forms → surface forms.

把 reader sugar (``'x``, `` `x ``, ``,x``, ``,@x``) 重写为 canonical form。
"""

from __future__ import annotations

from typing import cast

from qy.build.artifact import RawFormProgram
from qy.build.artifact import SurfaceProgram
from qy.frontend.surface import expand_surface_dialect
from qy.passes.pass_base import Pass
from qy.passes.pass_base import PassContext
from qy.passes.pass_base import PassResult

__all__ = ["SurfaceNormalizePass"]


class SurfaceNormalizePass(Pass):
    input_kind = "raw-forms"
    output_kind = "surface-forms"

    def __init__(self) -> None:
        super().__init__("frontend.surface_normalize")

    def run(self, context: PassContext) -> PassResult:
        raw_program = cast(RawFormProgram, context.input_artifact)
        normalized = expand_surface_dialect(list(raw_program.forms))
        return PassResult(
            success=True,
            artifact=SurfaceProgram(forms=tuple(normalized)),
            artifact_kind=self.output_kind,
        )
