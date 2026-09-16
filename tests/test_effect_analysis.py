# coding: utf-8
"""effect.analyze pass 的静态事实测试。."""

from __future__ import annotations

from qy.build.pipeline import compile_source_to_kind
from qy.build.pipeline import hir_artifact
from qy.passes.effect.analyze import EffectAnalysis
from qy.passes.effect.analyze import analyze_effects
from qy.passes.pass_base import PipelineSession


def _analyze(source: str) -> EffectAnalysis:
    result = compile_source_to_kind(source, PipelineSession(), kind="hir")
    return analyze_effects(hir_artifact(result))


def test_handled_effect_facts():
    analysis = _analyze(
        """
        (defeffect ask)
        (handle (+ 1 (perform ask 41)) ((ask (arg k) (resume k arg))))
        """
    )

    assert analysis.declared_resumable == {"ask": True}
    assert analysis.performed == frozenset({"ask"})
    assert analysis.handled == frozenset({"ask"})
    assert analysis.escaping == frozenset()
    assert analysis.discarded_continuations == ()
    assert analysis.multi_shot_resumes == ()


def test_performed_without_handler_is_escaping():
    analysis = _analyze("(defeffect ask)\n(perform ask 1)\n")

    assert analysis.performed == frozenset({"ask"})
    assert analysis.handled == frozenset()
    assert analysis.escaping == frozenset({"ask"})


def test_handler_without_resume_is_discarded_continuation():
    analysis = _analyze(
        """
        (defeffect ask)
        (handle (+ 1 (perform ask 41)) ((ask (arg k) 0)))
        """
    )

    assert analysis.discarded_continuations == ("ask",)


def test_multiple_resumes_are_reported():
    analysis = _analyze(
        """
        (defeffect ask)
        (handle (+ 1 (perform ask 41)) ((ask (arg k) (resume k (+ (resume k arg) 1)))))
        """
    )

    assert analysis.multi_shot_resumes == ("ask",)


def test_parallel_performs_are_reported():
    analysis = _analyze(
        """
        (defeffect ask)
        (parallel (perform ask 1) (perform ask 2))
        """
    )

    assert analysis.parallel_performs == frozenset({"ask"})


def test_effect_analyze_pass_emits_hint_for_escaping_effect():
    from qy.passes.pass_base import PassContext

    result = compile_source_to_kind(
        "(defeffect ask)\n(perform ask 1)\n", PipelineSession(), kind="hir"
    )
    program = hir_artifact(result)

    from qy.passes.effect.analyze import EffectAnalyzePass

    pass_result = EffectAnalyzePass().run(
        PassContext(input_artifact=program, artifact_kind="hir", session=PipelineSession())
    )

    hints = [d for d in pass_result.diagnostics if d.severity == "hint"]
    assert any("ask" in d.message for d in hints)
