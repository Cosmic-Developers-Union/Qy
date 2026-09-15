# coding: utf-8 -*-
"""``hir.validate`` pass.

校验 HIR 的结构良构性，对应 ``docs/hir-spec.md`` §4 中编号 H1..H14 的
所有不变量。谓词函数实现在 :mod:`qy.ir.hir.predicates`。

设计：

- 该 pass 是 ``Pipeline`` 中的常规 Pass，``input_kind="hir"``、
  ``output_kind="hir-validated"``、``name="hir.validate"``。
- 调用 :func:`qy.ir.hir.predicates.check_program` 全套检查并把诊断附加到
  ``ProgramIR.diagnostics``。
- ``success`` 当且仅当新产生的诊断中无 ``severity == "error"``；warning 不
  影响 success（参见 :data:`qy.ir.hir.predicates.H4_SEVERITY` 注释）。

修改历史：

- Phase 1 (formal-proofs)：从占位 stub 升级为真正的 verifier pass。
"""

from __future__ import annotations

from typing import cast

from qy.ir.hir import ProgramIR
from qy.ir.hir.predicates import check_program
from qy.passes.pass_base import Pass
from qy.passes.pass_base import PassContext
from qy.passes.pass_base import PassResult

__all__ = ["ValidateHIRPass"]


class ValidateHIRPass(Pass):
    input_kind = "hir"
    output_kind = "hir"

    def __init__(self) -> None:
        super().__init__("hir.validate")

    def run(self, context: PassContext) -> PassResult:
        program = cast(ProgramIR, context.input_artifact)
        env = context.session.env
        profile_effects = env.effect_names() if env is not None else frozenset()
        diagnostics = check_program(program, profile_effects=profile_effects)
        validated = ProgramIR(
            body=program.body,
            diagnostics=(*program.diagnostics, *diagnostics),
        )
        return PassResult(
            success=not any(d.severity == "error" for d in diagnostics),
            artifact=validated,
            artifact_kind=self.output_kind,
            diagnostics=diagnostics,
        )
