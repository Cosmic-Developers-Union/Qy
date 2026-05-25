# coding: utf-8
"""``frontend.reader_macro`` —— ``CstProgram`` → raw forms.

驱动 ``read_cst`` 将 CST 转换为 raw form 列表，并通过 session 的
``reader_macro_registry`` 解析 tagged literal 等 reader macro。
"""

from __future__ import annotations

from typing import cast

from qy.diag import Diagnostic
from qy.errors import QySyntaxError
from qy.frontend.cst import CstProgram
from qy.frontend.reader import read_cst
from qy.passes.pass_base import Pass
from qy.passes.pass_base import PassContext
from qy.passes.pass_base import PassResult

__all__ = ["ReaderMacroPass"]


class ReaderMacroPass(Pass):
    input_kind = "cst"
    output_kind = "raw-forms"

    def __init__(self) -> None:
        super().__init__("frontend.reader_macro")

    def run(self, context: PassContext) -> PassResult:
        cst = cast(CstProgram, context.input_artifact)
        registry = context.session.reader_macro_registry
        try:
            forms = read_cst(cst, registry=registry)
        except QySyntaxError as e:
            diag = Diagnostic(
                str(e),
                "error",
                line=getattr(e, "line", None),
                column=getattr(e, "column", None),
            )
            return PassResult(
                success=False,
                artifact=[],
                artifact_kind=self.output_kind,
                diagnostics=(diag,),
            )
        return PassResult(
            success=True,
            artifact=forms,
            artifact_kind=self.output_kind,
        )
