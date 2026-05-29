# coding: utf-8
"""``frontend.cst_parse`` —— source string → ``CstProgram``.

仅做 trivia-preserving 的 CST 解析，不展开任何 reader macro 或 surface sugar。
"""

from __future__ import annotations

from typing import cast

from qy.diag import Diagnostic
from qy.errors import QySyntaxError
from qy.errors import SourceSpan
from qy.frontend.cst import CstProgram
from qy.frontend.cst_parser import parse_cst
from qy.passes.pass_base import Pass
from qy.passes.pass_base import PassContext
from qy.passes.pass_base import PassResult

__all__ = ["CstParsePass"]


class CstParsePass(Pass):
    input_kind = "source"
    output_kind = "cst"

    def __init__(self) -> None:
        super().__init__("frontend.cst_parse")

    def run(self, context: PassContext) -> PassResult:
        source = cast(str, context.input_artifact)
        source_name = context.session.source_name
        try:
            program = parse_cst(source, source_name=source_name)
        except QySyntaxError as e:
            diag = Diagnostic(
                str(e),
                "error",
                line=getattr(e, "line", None),
                column=getattr(e, "column", None),
                span=getattr(e, "span", None),
            )
            return PassResult(
                success=False,
                artifact=CstProgram(children=(), trailing_trivia="", span=SourceSpan(source_name)),
                artifact_kind=self.output_kind,
                diagnostics=(diag,),
            )
        return PassResult(
            success=True,
            artifact=program,
            artifact_kind=self.output_kind,
        )
