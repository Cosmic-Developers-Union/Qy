# coding: utf-8
"""Default compilation pipeline orchestration."""

from __future__ import annotations

from collections.abc import Sequence

from qy.async_utils import run_coro
from qy.backend.vm.bytecode import BytecodeProgram
from qy.build.artifact import BYTECODE
from qy.build.artifact import CORE_AST
from qy.build.artifact import CST
from qy.build.artifact import HIR
from qy.build.artifact import LIR
from qy.build.artifact import MIR
from qy.build.artifact import RAW_FORMS
from qy.build.artifact import SOURCE
from qy.build.artifact import SURFACE_FORMS
from qy.build.artifact import RawFormProgram
from qy.build.artifact import SurfaceProgram
from qy.core.program import CoreProgram
from qy.frontend.cst import CstProgram
from qy.frontend.form import Form
from qy.ir import ProgramIR
from qy.ir.lir import LIRProgram
from qy.ir.mir import MIRProgram
from qy.passes.emit.bytecode import EmitBytecodePass
from qy.passes.frontend.cst_parse import CstParsePass
from qy.passes.frontend.reader_macro import ReaderMacroPass
from qy.passes.frontend.surface_normalize import SurfaceNormalizePass
from qy.passes.hir.lower_pass import LowerHIRPass
from qy.passes.lir.lower_pass import LowerLIRPass
from qy.passes.lir.verify import VerifyLIRPass
from qy.passes.macro.expand import MacroExpandPass
from qy.passes.mir.lower_pass import LowerMIRPass
from qy.passes.mir.validate import ValidateMIRPass
from qy.passes.pass_base import PassContext
from qy.passes.pass_base import PassResult
from qy.passes.pass_base import PipelineOptions
from qy.passes.pass_base import PipelineSession
from qy.passes.pipeline import Pipeline

__all__ = [
    "ARTIFACT_KIND_TO_TARGET_PASS",
    "build_default_pipeline",
    "bytecode_artifact",
    "compile_core_forms_to_bytecode_async",
    "compile_forms_to_bytecode_async",
    "compile_source_to_bytecode",
    "compile_source_to_bytecode_async",
    "compile_source_to_kind",
    "compile_source_to_kind_async",
    "core_ast_artifact",
    "cst_artifact",
    "hir_artifact",
    "lir_artifact",
    "mir_artifact",
    "raw_forms_artifact",
    "surface_forms_artifact",
]

ARTIFACT_KIND_TO_TARGET_PASS: dict[str, str] = {
    CST: "frontend.cst_parse",
    RAW_FORMS: "frontend.reader_macro",
    SURFACE_FORMS: "frontend.surface_normalize",
    CORE_AST: "macro.expand",
    HIR: "hir.lower",
    MIR: "mir.validate",
    LIR: "lir.verify",
    BYTECODE: "emit.bytecode",
}


def build_default_pipeline() -> Pipeline:
    pipeline = Pipeline()
    pipeline.add_pass(CstParsePass())
    pipeline.add_pass(ReaderMacroPass())
    pipeline.add_pass(SurfaceNormalizePass())
    pipeline.add_pass(MacroExpandPass())
    pipeline.add_pass(LowerHIRPass())
    pipeline.add_pass(LowerMIRPass())
    pipeline.add_pass(ValidateMIRPass())
    pipeline.add_pass(LowerLIRPass())
    pipeline.add_pass(VerifyLIRPass())
    pipeline.add_pass(EmitBytecodePass())
    return pipeline


def compile_source_to_bytecode(
    source: str,
    session: PipelineSession,
    *,
    options: PipelineOptions | None = None,
) -> PassResult:
    return run_coro(compile_source_to_bytecode_async(source, session, options=options))


async def compile_source_to_bytecode_async(
    source: str,
    session: PipelineSession,
    *,
    options: PipelineOptions | None = None,
) -> PassResult:
    pipeline = build_default_pipeline()
    context = _make_context(source, SOURCE, session, options)
    return await pipeline.run_async(context)


async def compile_forms_to_bytecode_async(
    forms: Sequence[Form],
    session: PipelineSession,
    *,
    options: PipelineOptions | None = None,
) -> PassResult:
    pipeline = build_default_pipeline().subset(start="macro.expand")
    artifact = SurfaceProgram(forms=tuple(forms))
    context = _make_context(artifact, SURFACE_FORMS, session, options)
    return await pipeline.run_async(context)


async def compile_core_forms_to_bytecode_async(
    forms: Sequence[Form],
    session: PipelineSession,
    *,
    options: PipelineOptions | None = None,
) -> PassResult:
    pipeline = build_default_pipeline().subset(start="hir.lower")
    artifact = CoreProgram(forms=tuple(forms))
    context = _make_context(artifact, CORE_AST, session, options)
    return await pipeline.run_async(context)


async def compile_source_to_kind_async(
    source: str,
    session: PipelineSession,
    *,
    kind: str,
    options: PipelineOptions | None = None,
) -> PassResult:
    if kind not in ARTIFACT_KIND_TO_TARGET_PASS:
        raise ValueError(
            f"unknown artifact kind {kind!r}; valid kinds: {sorted(ARTIFACT_KIND_TO_TARGET_PASS)}"
        )
    end_pass = ARTIFACT_KIND_TO_TARGET_PASS[kind]
    pipeline = build_default_pipeline().subset(end=end_pass)
    context = _make_context(source, SOURCE, session, options)
    return await pipeline.run_async(context)


def compile_source_to_kind(
    source: str,
    session: PipelineSession,
    *,
    kind: str,
    options: PipelineOptions | None = None,
) -> PassResult:
    return run_coro(compile_source_to_kind_async(source, session, kind=kind, options=options))


def _make_context(
    artifact: object,
    kind: str,
    session: PipelineSession,
    options: PipelineOptions | None,
) -> PassContext:
    return PassContext(
        input_artifact=artifact,
        artifact_kind=kind,
        session=session,
        diagnostics=(),
        options=options or PipelineOptions(error_threshold=10**6),
    )


def cst_artifact(result: PassResult) -> CstProgram:
    artifact = result.artifact
    if not isinstance(artifact, CstProgram):
        raise TypeError(f"expected CstProgram from pipeline, got {type(artifact).__name__}")
    return artifact


def raw_forms_artifact(result: PassResult) -> RawFormProgram:
    artifact = result.artifact
    if not isinstance(artifact, RawFormProgram):
        raise TypeError(f"expected RawFormProgram from pipeline, got {type(artifact).__name__}")
    return artifact


def surface_forms_artifact(result: PassResult) -> SurfaceProgram:
    artifact = result.artifact
    if not isinstance(artifact, SurfaceProgram):
        raise TypeError(f"expected SurfaceProgram from pipeline, got {type(artifact).__name__}")
    return artifact


def core_ast_artifact(result: PassResult) -> CoreProgram:
    artifact = result.artifact
    if not isinstance(artifact, CoreProgram):
        raise TypeError(f"expected CoreProgram from pipeline, got {type(artifact).__name__}")
    return artifact


def hir_artifact(result: PassResult) -> ProgramIR:
    artifact = result.artifact
    if not isinstance(artifact, ProgramIR):
        raise TypeError(f"expected ProgramIR from pipeline, got {type(artifact).__name__}")
    return artifact


def mir_artifact(result: PassResult) -> MIRProgram:
    artifact = result.artifact
    if not isinstance(artifact, MIRProgram):
        raise TypeError(f"expected MIRProgram from pipeline, got {type(artifact).__name__}")
    return artifact


def lir_artifact(result: PassResult) -> LIRProgram:
    artifact = result.artifact
    if not isinstance(artifact, LIRProgram):
        raise TypeError(f"expected LIRProgram from pipeline, got {type(artifact).__name__}")
    return artifact


def bytecode_artifact(result: PassResult) -> BytecodeProgram:
    artifact = result.artifact
    if not isinstance(artifact, BytecodeProgram):
        raise TypeError(f"expected BytecodeProgram from pipeline, got {type(artifact).__name__}")
    return artifact
