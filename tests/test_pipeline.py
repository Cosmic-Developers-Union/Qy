# coding: utf-8
"""测试 qy.passes.pipeline 模块。."""

from __future__ import annotations

import asyncio
from typing import cast

import pytest

from qy.backend.vm.bytecode import BytecodeProgram
from qy.build.artifact import RawFormProgram
from qy.build.artifact import SurfaceProgram
from qy.build.pipeline import build_default_pipeline
from qy.build.pipeline import compile_core_forms_to_bytecode_async
from qy.build.pipeline import compile_forms_to_bytecode_async
from qy.build.pipeline import compile_source_to_kind_async
from qy.build.pipeline import raw_forms_artifact
from qy.build.pipeline import surface_forms_artifact
from qy.core.program import CoreProgram
from qy.diag import Diagnostic
from qy.frontend.cst import CstProgram
from qy.frontend.reader import Symbol
from qy.ir import ProgramIR
from qy.ir.lir import LIRProgram
from qy.ir.mir import MIRProgram
from qy.passes.pass_base import Pass
from qy.passes.pass_base import PassContext
from qy.passes.pass_base import PassResult
from qy.passes.pass_base import PipelineOptions
from qy.passes.pass_base import PipelineSession
from qy.passes.pipeline import Pipeline
from qy.runtime import Qy


class MockPass(Pass):
    """Mock pass that appends its name to a string artifact."""

    input_kind = ""  # accept any
    output_kind = ""  # propagate

    def __init__(
        self,
        name: str,
        *,
        should_fail: bool = False,
        diagnostics: tuple[Diagnostic, ...] = (),
    ):
        super().__init__(name)
        self.should_fail = should_fail
        self.diagnostics = diagnostics
        self.executed = False

    def run(self, context: PassContext) -> PassResult:
        self.executed = True
        if self.should_fail:
            return PassResult(
                success=False,
                artifact=context.input_artifact,
                artifact_kind=context.artifact_kind,
                diagnostics=self.diagnostics,
            )
        new_artifact = f"{context.input_artifact}+{self.name}"
        return PassResult(
            success=True,
            artifact=new_artifact,
            artifact_kind=context.artifact_kind,
            diagnostics=self.diagnostics,
        )


def _ctx(artifact: object = "initial", **kwargs: object) -> PassContext:
    artifact_kind = cast(str, kwargs.pop("artifact_kind", ""))
    session = cast(PipelineSession, kwargs.pop("session", PipelineSession.minimal()))
    diagnostics = cast(tuple[Diagnostic, ...], kwargs.pop("diagnostics", ()))
    options = cast(PipelineOptions, kwargs.pop("options", PipelineOptions()))
    return PassContext(
        input_artifact=artifact,
        artifact_kind=artifact_kind,
        session=session,
        diagnostics=diagnostics,
        options=options,
    )


def test_pipeline_creation():
    pipeline = Pipeline()
    assert pipeline.passes == []


def test_pipeline_add_pass():
    pipeline = Pipeline()
    pass1 = MockPass("pass1")
    pass2 = MockPass("pass2")

    pipeline.add_pass(pass1)
    assert len(pipeline.passes) == 1
    assert pipeline.passes[0] is pass1

    pipeline.add_pass(pass2)
    assert len(pipeline.passes) == 2
    assert pipeline.passes[1] is pass2


def test_pipeline_add_pass_chains():
    pipeline = Pipeline()
    pass1 = MockPass("pass1")
    assert pipeline.add_pass(pass1) is pipeline


def test_pipeline_run_empty():
    pipeline = Pipeline()
    result = pipeline.run(_ctx("initial"))
    assert result.success is True
    assert result.artifact == "initial"
    assert result.diagnostics == ()


def test_pipeline_run_single_pass():
    pipeline = Pipeline()
    pass1 = MockPass("pass1")
    pipeline.add_pass(pass1)

    result = pipeline.run(_ctx("initial"))

    assert pass1.executed is True
    assert result.success is True
    assert result.artifact == "initial+pass1"
    assert result.diagnostics == ()


def test_pipeline_run_multiple_passes():
    pipeline = Pipeline()
    pass1 = MockPass("pass1")
    pass2 = MockPass("pass2")
    pass3 = MockPass("pass3")

    pipeline.add_pass(pass1).add_pass(pass2).add_pass(pass3)

    result = pipeline.run(_ctx("initial"))

    assert pass1.executed is True
    assert pass2.executed is True
    assert pass3.executed is True
    assert result.success is True
    assert result.artifact == "initial+pass1+pass2+pass3"


def test_pipeline_stops_on_failure():
    pipeline = Pipeline()
    pass1 = MockPass("pass1")
    pass2 = MockPass("pass2", should_fail=True)
    pass3 = MockPass("pass3")

    pipeline.add_pass(pass1).add_pass(pass2).add_pass(pass3)

    result = pipeline.run(_ctx("initial"))

    assert pass1.executed is True
    assert pass2.executed is True
    assert pass3.executed is False
    assert result.success is False
    assert result.artifact == "initial+pass1"


def test_pipeline_run_with_target_short_circuits():
    pipeline = Pipeline()
    pass1 = MockPass("pass1")
    pass2 = MockPass("pass2")
    pass3 = MockPass("pass3")

    pipeline.add_pass(pass1).add_pass(pass2).add_pass(pass3)

    result = pipeline.run(
        _ctx("initial", options=PipelineOptions(target="pass2")),
    )

    assert pass1.executed is True
    assert pass2.executed is True
    assert pass3.executed is False
    assert result.success is True
    assert result.artifact == "initial+pass1+pass2"


def test_pipeline_dump_sink_called_after_match():
    pipeline = Pipeline()
    pipeline.add_pass(MockPass("pass1")).add_pass(MockPass("pass2")).add_pass(MockPass("pass3"))

    captured: list[tuple[str, object]] = []

    def sink(name: str, artifact: object) -> None:
        captured.append((name, artifact))

    result = pipeline.run(
        _ctx("initial", options=PipelineOptions(after="pass2", dump_sink=sink)),
    )

    assert captured == [("pass2", "initial+pass1+pass2")]
    assert result.success is True
    assert result.artifact == "initial+pass1+pass2+pass3"


def test_pipeline_dump_sink_silent_without_match():
    pipeline = Pipeline()
    pipeline.add_pass(MockPass("a")).add_pass(MockPass("b"))

    captured: list[tuple[str, object]] = []

    def sink(name: str, artifact: object) -> None:
        captured.append((name, artifact))

    pipeline.run(_ctx("x", options=PipelineOptions(after="missing", dump_sink=sink)))

    assert captured == []


def test_pipeline_error_threshold_short_circuits():
    pipeline = Pipeline()
    diag_error = Diagnostic("oops", "error")
    pass1 = MockPass("pass1", diagnostics=(diag_error,))
    pass2 = MockPass("pass2")

    pipeline.add_pass(pass1).add_pass(pass2)

    result = pipeline.run(_ctx("initial"))

    assert pass1.executed is True
    assert pass2.executed is False
    assert result.success is False
    assert any(d.message == "oops" for d in result.diagnostics)


def test_pipeline_error_threshold_higher_allows_continue():
    pipeline = Pipeline()
    diag_error = Diagnostic("oops", "error")
    pass1 = MockPass("pass1", diagnostics=(diag_error,))
    pass2 = MockPass("pass2")

    pipeline.add_pass(pass1).add_pass(pass2)

    result = pipeline.run(
        _ctx("initial", options=PipelineOptions(error_threshold=2)),
    )

    assert pass1.executed is True
    assert pass2.executed is True
    # Pipeline.run still reports failure when *any* error accumulated by the end,
    # but threshold gates only short-circuiting.
    assert any(d.message == "oops" for d in result.diagnostics)


def test_pipeline_warning_does_not_short_circuit():
    pipeline = Pipeline()
    diag_warn = Diagnostic("careful", "warning")
    pass1 = MockPass("pass1", diagnostics=(diag_warn,))
    pass2 = MockPass("pass2")

    pipeline.add_pass(pass1).add_pass(pass2)

    result = pipeline.run(_ctx("initial"))

    assert pass1.executed is True
    assert pass2.executed is True
    assert result.success is True
    assert any(d.severity == "warning" for d in result.diagnostics)


def test_pipeline_subset_returns_partial_pipeline():
    pipeline = Pipeline()
    pass1 = MockPass("pass1")
    pass2 = MockPass("pass2")
    pass3 = MockPass("pass3")

    pipeline.add_pass(pass1).add_pass(pass2).add_pass(pass3)

    sub = pipeline.subset(start="pass2", end="pass3")
    assert [p.name for p in sub.passes] == ["pass2", "pass3"]
    # original is untouched
    assert [p.name for p in pipeline.passes] == ["pass1", "pass2", "pass3"]

    result = sub.run(_ctx("seed"))
    assert result.artifact == "seed+pass2+pass3"


def test_pipeline_subset_unknown_pass_raises():
    pipeline = Pipeline()
    pipeline.add_pass(MockPass("pass1"))
    with pytest.raises(ValueError, match="unknown pass"):
        pipeline.subset(start="missing")


def test_pipeline_subset_inverted_raises():
    pipeline = Pipeline()
    pipeline.add_pass(MockPass("a")).add_pass(MockPass("b"))
    with pytest.raises(ValueError, match="comes after"):
        pipeline.subset(start="b", end="a")


class _StrictKindPass(Pass):
    """Pass with strict input/output kinds for kind-mismatch testing."""

    def __init__(self, name: str, input_kind: str, output_kind: str) -> None:
        super().__init__(name)
        self.input_kind = input_kind
        self.output_kind = output_kind

    def run(self, context: PassContext) -> PassResult:
        return PassResult(
            success=True,
            artifact=context.input_artifact,
            artifact_kind=self.output_kind,
        )


def test_pipeline_artifact_kind_mismatch_fail_fast():
    pipeline = Pipeline()
    pipeline.add_pass(_StrictKindPass("a", "source", "raw"))
    pipeline.add_pass(_StrictKindPass("b", "hir", "mir"))

    result = pipeline.run(_ctx("seed", artifact_kind="source"))

    assert result.success is False
    assert any("expects artifact kind" in d.message for d in result.diagnostics)


def test_pipeline_first_pass_accepts_blank_kind():
    """First pass runs even when context.artifact_kind is empty (compat path)."""
    pipeline = Pipeline()
    pipeline.add_pass(_StrictKindPass("a", "source", "raw"))

    result = pipeline.run(_ctx("seed"))
    assert result.success is True


def test_pipeline_run_sync_rejects_async_pass():
    class AsyncPass(Pass):
        def __init__(self) -> None:
            super().__init__("async")

        async def run(self, context: PassContext) -> PassResult:  # type: ignore[override]
            return PassResult(success=True, artifact=context.input_artifact)

    pipeline = Pipeline()
    pipeline.add_pass(AsyncPass())

    with pytest.raises(TypeError, match="awaitable"):
        pipeline.run(_ctx("x"))


def test_pipeline_run_async_handles_async_pass():
    class AsyncPass(Pass):
        def __init__(self) -> None:
            super().__init__("a")

        async def run(self, context: PassContext) -> PassResult:  # type: ignore[override]
            return PassResult(
                success=True,
                artifact=f"{context.input_artifact}+async",
            )

    pipeline = Pipeline()
    pipeline.add_pass(AsyncPass()).add_pass(MockPass("sync"))

    result = asyncio.run(pipeline.run_async(_ctx("seed")))
    assert result.success is True
    assert result.artifact == "seed+async+sync"


def test_default_pipeline_stage_order():
    pipeline = build_default_pipeline()
    assert [p.name for p in pipeline.passes] == [
        "frontend.cst_parse",
        "frontend.reader_macro",
        "frontend.surface_normalize",
        "macro.expand",
        "hir.lower",
        "mir.lower",
        "mir.validate",
        "lir.lower",
        "lir.verify",
        "emit.bytecode",
    ]


@pytest.mark.parametrize(
    ("kind", "expected_type"),
    [
        ("cst", CstProgram),
        ("raw-forms", RawFormProgram),
        ("surface-forms", SurfaceProgram),
        ("core-ast", CoreProgram),
        ("hir", ProgramIR),
        ("mir", MIRProgram),
        ("lir", LIRProgram),
        ("bytecode", BytecodeProgram),
    ],
)
def test_compile_source_to_kind_returns_typed_artifact(kind: str, expected_type: type[object]):
    qy = Qy()
    session = PipelineSession(env=qy.env)
    result = asyncio.run(compile_source_to_kind_async("(+ 1 2)", session, kind=kind))
    assert result.success is True
    assert isinstance(result.artifact, expected_type)


def test_raw_and_surface_extractors_return_wrapped_forms():
    qy = Qy()
    session = PipelineSession(env=qy.env)
    raw_result = asyncio.run(compile_source_to_kind_async("(+ 1 2)", session, kind="raw-forms"))
    raw = raw_forms_artifact(raw_result)
    assert isinstance(raw, RawFormProgram)
    assert isinstance(raw.forms, tuple)

    surface_result = asyncio.run(
        compile_source_to_kind_async("(+ 1 2)", PipelineSession(env=qy.env), kind="surface-forms")
    )
    surface = surface_forms_artifact(surface_result)
    assert isinstance(surface, SurfaceProgram)
    assert isinstance(surface.forms, tuple)


def test_form_entrypoints_compile_through_bytecode():
    qy = Qy()
    symbol = Symbol
    forms_result = asyncio.run(
        compile_forms_to_bytecode_async(
            [(symbol("+"), symbol("1"), symbol("2"))],
            PipelineSession(env=qy.env),
        )
    )
    assert isinstance(forms_result.artifact, BytecodeProgram)

    core_result = asyncio.run(
        compile_core_forms_to_bytecode_async([symbol("1")], PipelineSession(env=qy.env))
    )
    assert isinstance(core_result.artifact, BytecodeProgram)
