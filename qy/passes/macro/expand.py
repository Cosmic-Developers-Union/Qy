# coding: utf-8
"""``macro.expand`` —— surface forms → ``CoreProgram``.

异步包装 ``qy.macro.expand.macroexpand_async``，把展开结果包成 ``CoreProgram``。
"""

from __future__ import annotations

from typing import cast

from qy.core.program import CoreProgram
from qy.frontend.reader import Form
from qy.macro.expand import MacroExpansionOptions
from qy.macro.expand import macroexpand_async
from qy.passes.pass_base import Pass
from qy.passes.pass_base import PassContext
from qy.passes.pass_base import PassResult

__all__ = ["MacroExpandPass"]


class MacroExpandPass(Pass):
    input_kind = "surface-forms"
    output_kind = "core-ast"

    def __init__(self) -> None:
        super().__init__("macro.expand")

    async def run(self, context: PassContext) -> PassResult:
        forms = cast(list[Form], context.input_artifact)
        options = context.session.macro_options
        if options is None:
            options = MacroExpansionOptions()
        expansion = await macroexpand_async(forms, context.session.env, options=options)
        program = CoreProgram(forms=tuple(expansion.forms), traces=tuple(expansion.traces))
        return PassResult(
            success=True,
            artifact=program,
            artifact_kind=self.output_kind,
            diagnostics=tuple(expansion.diagnostics),
        )
