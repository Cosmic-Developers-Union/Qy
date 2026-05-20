# coding: utf-8
"""静态分析包。.

提供作用域追踪、类型推断、参数数量检查等静态分析能力。
不执行 runtime evaluation。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from qy.environment import Environment

from qy.analysis.infer import infer
from qy.analysis.scope import predeclare_callable_definitions
from qy.analysis.scope import scope_after_form
from qy.analysis.scope import scope_from_environment
from qy.diag import Diagnostic
from qy.environment import standard_environment
from qy.reader import Form
from qy.reader import ReaderSyntaxError
from qy.reader import read

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


def analyze_source(source: str, env: Environment | None = None) -> Analysis:
    try:
        forms = read(source)
    except ReaderSyntaxError as e:
        return Analysis(
            [],
            [Diagnostic(str(e), "error", line=e.line, column=e.column)],
        )
    return analyze(forms, env)


def analyze(forms: list[Form], env: Environment | None = None) -> Analysis:
    env = env or standard_environment()
    diagnostics: list[Diagnostic] = []
    scope = predeclare_callable_definitions(tuple(forms), scope_from_environment(env))
    for form in forms:
        infer(form, env, scope, diagnostics)
        scope = scope_after_form(form, env, scope)
    return Analysis(forms, diagnostics)


def type_check_source(source: str, env: Environment | None = None) -> list[Diagnostic]:
    return analyze_source(source, env).diagnostics
