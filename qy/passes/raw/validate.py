# coding: utf-8
"""raw.validate pass。.

目标：
- 校验 raw AST 只包含 ``Symbol`` 与不可变 ``Chain``（空链是 ``QyNil``）；
- 校验 improper chain 的尾部仍是 datum，而不是宿主值。

当前：
- 已实现。这是 raw AST 不变量的守卫：reader 不得把 runtime value 提前塞进
  raw AST（见 AGENTS.md / docs/pipeline.md 跨层禁止规则）。
- 该 pass 位于 ``frontend.reader_macro`` 之后、``frontend.surface_normalize``
  之前，因此 surface dialect 与 macro expand 都在已验证的 datum 上工作。

禁止：
- 不执行 runtime evaluation；
- 不修正 raw AST（发现非法节点直接产出 error diagnostic）。
"""

from __future__ import annotations

from typing import cast

from qy.build.artifact import RawFormProgram
from qy.core.syntax import QyNil
from qy.core.syntax import Symbol
from qy.core.syntax import car
from qy.core.syntax import cdr
from qy.core.syntax import get_span
from qy.core.syntax import is_chain
from qy.diag import Diagnostic
from qy.passes.pass_base import Pass
from qy.passes.pass_base import PassContext
from qy.passes.pass_base import PassResult

__all__ = ["ValidateRawPass", "validate_raw_forms"]


def validate_raw_forms(forms: tuple[object, ...]) -> tuple[Diagnostic, ...]:
    """Return diagnostics for any raw AST node that is not symbol/chain/nil."""
    diagnostics: list[Diagnostic] = []

    def _visit(value: object) -> None:
        if isinstance(value, Symbol | QyNil):
            return
        if is_chain(value):
            _visit(car(value))
            _visit(cdr(value))
            return
        diagnostics.append(
            Diagnostic(
                f"raw AST may only contain symbol/chain/nil, got {type(value).__name__} ({value!r})",
                "error",
                span=get_span(value),
            )
        )

    for form in forms:
        _visit(form)
    return tuple(diagnostics)


class ValidateRawPass(Pass):
    input_kind = "raw-forms"
    output_kind = "raw-forms"

    def __init__(self) -> None:
        super().__init__("raw.validate")

    def run(self, context: PassContext) -> PassResult:
        program = cast(RawFormProgram, context.input_artifact)
        diagnostics = validate_raw_forms(program.forms)
        has_errors = any(diagnostic.severity == "error" for diagnostic in diagnostics)
        return PassResult(
            success=not has_errors,
            artifact=program,
            artifact_kind=self.output_kind,
            diagnostics=diagnostics,
        )
