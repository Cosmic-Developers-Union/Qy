# coding: utf-8
"""静态分析包。.

提供作用域追踪、参数数量检查、effect/module 良构性检查等静态分析能力。
不执行 runtime evaluation。

语义真源是 pipeline 本身：源码先经 canonical frontend（CST -> raw ->
surface -> macro expand）得到 core forms，再 lower 到 HIR 并运行 H1-H14
verifier。analyzer 不再维护第二套语法 / 宏 / 作用域解释，避免与 lowering
各自发明语义。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from qy.frontend.reader import Form
    from qy.session.runtime_space import RuntimeSpace as Environment

from qy.diag import Diagnostic
from qy.session.runtime_space import create_standard_runtime_space as standard_environment

__all__ = [
    "Analysis",
    "Diagnostic",
    "analyze",
    "analyze_source",
    "type_check_source",
]


@dataclass(frozen=True, slots=True)
class Analysis:
    forms: list[Form]
    diagnostics: list[Diagnostic]

    @property
    def ok(self) -> bool:
        return not any(diagnostic.severity == "error" for diagnostic in self.diagnostics)


def analyze(forms: list[Form], env: Environment | None = None) -> Analysis:
    """检查已经过 macro expand 的 core forms。.

    与执行路径共用 ``hir.lower``，并运行 H1-H14 verifier；不重新解释语法。
    """
    from qy.ir.hir.predicates import check_program
    from qy.passes.hir.lower import lower

    env = env or standard_environment()
    program = lower(list(forms), env)
    diagnostics = [
        *program.diagnostics,
        *check_program(program, profile_effects=env.effect_names()),
    ]
    return Analysis(list(forms), list(diagnostics))


def analyze_source(source: str, env: Environment | None = None) -> Analysis:
    """分析源码。.

    使用 canonical frontend 完成 CST 解析、surface dialect 与 macro expand，
    再在 core forms 上做 HIR lower + verifier。reader / macro / lowering 的
    诊断都来自真实 pipeline，因此 analyzer 与执行路径看到同一语言形态。
    """
    from qy.build.artifact import CORE_AST
    from qy.build.pipeline import compile_source_to_kind
    from qy.build.pipeline import core_ast_artifact
    from qy.passes.pass_base import PipelineSession

    env = env or standard_environment()
    result = compile_source_to_kind(source, PipelineSession(env=env), kind=CORE_AST)
    if not result.success:
        return Analysis([], list(result.diagnostics))
    core = core_ast_artifact(result)
    analysis = analyze(list(core.forms), env)
    if result.diagnostics:
        return Analysis(analysis.forms, [*result.diagnostics, *analysis.diagnostics])
    return analysis


def type_check_source(source: str, env: Environment | None = None) -> list[Diagnostic]:
    return analyze_source(source, env).diagnostics
