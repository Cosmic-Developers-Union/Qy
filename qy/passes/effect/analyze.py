# coding: utf-8
"""effect.analyze pass。.

目标：
- 产出 HIR 层的 effect 静态事实，作为后续 verifier / 优化 / LIR lowering 的基础：
  - ``declared``：``defeffect`` 声明的 effect 及其 ``resumable`` 属性；
  - ``performed`` / ``handled`` / ``escaping``：被执行、被处理、以及程序内无 handler
    的 effect 集合；
  - ``discarded_continuations``：resumable effect 的 handler 从不 ``resume``
    （abort 语义，属于合法但值得优化器知道的事实）；
  - ``multi_shot_resumes``：同一 handler 内出现多于一次 ``resume``（潜在 multi-shot）；
  - ``parallel_performs``：在 ``parallel`` / ``all`` / ``race`` 分支内执行的 effect。

当前：
- 已实现，且是只读 analysis pass：不改变 ``ProgramIR.body``。
- H6/H7/H8 负责"effect 是否声明 / handler 是否合法 / resume 位置与 resumable"的
  良构性；本 pass 只补充 H1–H14 不覆盖的 effect 事实与逃逸判断，两者不重复。
- 唯一的诊断是 EA1（hint 级）：effect 被执行但程序内没有任何 handler。

禁止：
- 不执行 runtime evaluation；
- 不做 effect lowering（effect lowering 属于 LIR 职责，见 docs/ir-design.md）。
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import fields
from dataclasses import is_dataclass
from typing import cast

from qy.diag import Diagnostic
from qy.ir.hir import AllExpr
from qy.ir.hir import DefeffectExpr
from qy.ir.hir import HandleExpr
from qy.ir.hir import ParallelExpr
from qy.ir.hir import PerformExpr
from qy.ir.hir import ProgramIR
from qy.ir.hir import RaceExpr
from qy.ir.hir import ResumeExpr
from qy.passes.pass_base import Pass
from qy.passes.pass_base import PassContext
from qy.passes.pass_base import PassResult

__all__ = ["EffectAnalysis", "EffectAnalyzePass", "analyze_effects"]


@dataclass(frozen=True, slots=True)
class EffectAnalysis:
    """静态 effect 事实。."""

    declared: tuple[tuple[str, bool], ...] = ()
    performed: frozenset[str] = frozenset()
    handled: frozenset[str] = frozenset()
    escaping: frozenset[str] = frozenset()
    discarded_continuations: tuple[str, ...] = ()
    multi_shot_resumes: tuple[str, ...] = ()
    parallel_performs: frozenset[str] = frozenset()

    @property
    def declared_resumable(self) -> dict[str, bool]:
        return dict(self.declared)


def _iter_dataclass_fields(node: object):
    if is_dataclass(node) and not isinstance(node, type):
        for field_info in fields(node):
            yield getattr(node, field_info.name)
    elif isinstance(node, tuple | list):
        yield from node


def _collect_declarations(body: tuple[object, ...]) -> dict[str, bool]:
    declared: dict[str, bool] = {}

    def _visit(node: object) -> None:
        if isinstance(node, DefeffectExpr):
            declared.setdefault(node.name.name, node.resumable)
            return
        for child in _iter_dataclass_fields(node):
            _visit(child)

    for item in body:
        _visit(item)
    return declared


def _count_resumes(node: object) -> int:
    if isinstance(node, ResumeExpr):
        return 1 + _count_resumes(node.continuation) + _count_resumes(node.value)
    count = 0
    for child in _iter_dataclass_fields(node):
        count += _count_resumes(child)
    return count


def analyze_effects(program: ProgramIR) -> EffectAnalysis:
    """Compute static effect facts for *program*."""
    declared = _collect_declarations(cast(tuple[object, ...], program.body))
    performed: set[str] = set()
    handled: set[str] = set()
    escaping: set[str] = set()
    discarded: list[str] = []
    multi_shot: list[str] = []
    parallel_performs: set[str] = set()

    def _walk(node: object, active: frozenset[str], *, parallel: bool) -> None:
        if isinstance(node, DefeffectExpr):
            return
        if isinstance(node, PerformExpr):
            name = node.effect.name
            performed.add(name)
            if parallel:
                parallel_performs.add(name)
            if name not in active:
                escaping.add(name)
            _walk(node.argument, active, parallel=parallel)
            return
        if isinstance(node, HandleExpr):
            names = frozenset(handler.effect.name for handler in node.handlers)
            for handler in node.handlers:
                handled.add(handler.effect.name)
                resumes = _count_resumes(handler.body)
                resumable = declared.get(handler.effect.name, True)
                if resumable and resumes == 0 and handler.effect.name not in discarded:
                    discarded.append(handler.effect.name)
                if resumes > 1 and handler.effect.name not in multi_shot:
                    multi_shot.append(handler.effect.name)
            # 被 handle 的表达式处于该 handler 的动态范围内；handler body 本身
            # 运行在 handler 之外，因此只继承外层 active 集合。
            _walk(node.expression, active | names, parallel=parallel)
            for handler in node.handlers:
                for item in handler.body:
                    _walk(item, active, parallel=parallel)
            return
        if isinstance(node, ParallelExpr | AllExpr | RaceExpr):
            for expr in node.exprs:
                _walk(expr, active, parallel=True)
            return
        for child in _iter_dataclass_fields(node):
            _walk(child, active, parallel=parallel)

    for item in program.body:
        _walk(item, frozenset(), parallel=False)

    return EffectAnalysis(
        declared=tuple(sorted(declared.items())),
        performed=frozenset(performed),
        handled=frozenset(handled),
        escaping=frozenset(escaping),
        discarded_continuations=tuple(sorted(discarded)),
        multi_shot_resumes=tuple(sorted(multi_shot)),
        parallel_performs=frozenset(parallel_performs),
    )


def _escaping_diagnostics(analysis: EffectAnalysis) -> tuple[Diagnostic, ...]:
    return tuple(
        Diagnostic(
            f"effect {name!r} is performed but no handler in this program handles it",
            "hint",
        )
        for name in sorted(analysis.escaping)
    )


class EffectAnalyzePass(Pass):
    input_kind = "hir"
    output_kind = "hir"

    def __init__(self) -> None:
        super().__init__("effect.analyze")

    def run(self, context: PassContext) -> PassResult:
        program = cast(ProgramIR, context.input_artifact)
        analysis = analyze_effects(program)
        return PassResult(
            success=True,
            artifact=program,
            artifact_kind=self.output_kind,
            diagnostics=_escaping_diagnostics(analysis),
        )
