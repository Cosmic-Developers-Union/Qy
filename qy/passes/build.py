# coding: utf-8
"""Pipeline 工厂。.

提供唯一入口 ``build_default_pipeline``，按 CLAUDE.md / LANGUAGE.md 中规定的
固定阶段顺序拼装：

    source
      → frontend.cst_parse        → cst
      → frontend.reader_macro     → raw-forms
      → frontend.surface_normalize → surface-forms
      → macro.expand              → core-ast
      → hir.lower                 → hir
      → mir.lower                 → mir
      → lir.lower                 → lir
      → emit.bytecode             → bytecode

所有执行入口（``qy.runtime``、``qy.vm.instance.machine``、CLI、benchmark、
LLVM 后端）必须通过这个工厂获取 Pipeline，禁止直接拼装 Pass 列表，更禁止
绕过 pipeline 直接调用 ``lower``/``lower_mir``/``compile_*_bytecode`` 等
旧入口。
"""

from __future__ import annotations

from qy.async_utils import run_coro
from qy.backend.vm.bytecode import BytecodeProgram
from qy.core.program import CoreProgram
from qy.ir import ProgramIR
from qy.ir.lir import LIRProgram
from qy.ir.mir import MIRProgram
from qy.passes.emit.bytecode import EmitBytecodePass
from qy.passes.frontend.cst_parse import CstParsePass
from qy.passes.frontend.reader_macro import ReaderMacroPass
from qy.passes.frontend.surface_normalize import SurfaceNormalizePass
from qy.passes.hir.lower_pass import LowerHIRPass
from qy.passes.lir.lower_pass import LowerLIRPass
from qy.passes.macro.expand import MacroExpandPass
from qy.passes.mir.lower_pass import LowerMIRPass
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
    "hir_artifact",
    "lir_artifact",
    "mir_artifact",
    "raw_forms_artifact",
    "surface_forms_artifact",
]


# 把 artifact-kind 映射到能产出该 artifact 的 pass 名 (Pipeline.subset 的 end 参数)。
ARTIFACT_KIND_TO_TARGET_PASS: dict[str, str] = {
    "cst": "frontend.cst_parse",
    "raw-forms": "frontend.reader_macro",
    "surface-forms": "frontend.surface_normalize",
    "core-ast": "macro.expand",
    "hir": "hir.lower",
    "mir": "mir.lower",
    "lir": "lir.lower",
    "bytecode": "emit.bytecode",
}


def build_default_pipeline() -> Pipeline:
    """构造完整 source→bytecode 的默认 pipeline。."""
    pipeline = Pipeline()
    pipeline.add_pass(CstParsePass())
    pipeline.add_pass(ReaderMacroPass())
    pipeline.add_pass(SurfaceNormalizePass())
    pipeline.add_pass(MacroExpandPass())
    pipeline.add_pass(LowerHIRPass())
    pipeline.add_pass(LowerMIRPass())
    pipeline.add_pass(LowerLIRPass())
    pipeline.add_pass(EmitBytecodePass())
    return pipeline


def compile_source_to_bytecode(
    source: str,
    session: PipelineSession,
    *,
    options: PipelineOptions | None = None,
) -> PassResult:
    """同步入口：source → BytecodeProgram。.

    ``macro.expand`` 是 async pass；该函数通过 ``run_coro`` 桥接。
    """
    return run_coro(compile_source_to_bytecode_async(source, session, options=options))


async def compile_source_to_bytecode_async(
    source: str,
    session: PipelineSession,
    *,
    options: PipelineOptions | None = None,
) -> PassResult:
    """从 source 起的完整 pipeline。."""
    pipeline = build_default_pipeline()
    context = _make_context(source, "source", session, options)
    return await pipeline.run_async(context)


async def compile_forms_to_bytecode_async(
    forms: list,
    session: PipelineSession,
    *,
    options: PipelineOptions | None = None,
) -> PassResult:
    """从已经 surface-normalize 的 forms 起；走 macro.expand → bytecode。.

    给 ``Qy.evaluate(form)`` / ``evaluate_form_async`` 这类输入是 python form 的入口使用。
    """
    pipeline = build_default_pipeline().subset(start="macro.expand")
    context = _make_context(forms, "surface-forms", session, options)
    return await pipeline.run_async(context)


async def compile_core_forms_to_bytecode_async(
    forms: list,
    session: PipelineSession,
    *,
    options: PipelineOptions | None = None,
) -> PassResult:
    """从已经 macro-expanded 的 forms 起；走 hir.lower → bytecode。.

    给 ``RUNTIME_EVAL`` 这类输入是运行时 form 的入口使用。
    """
    pipeline = build_default_pipeline().subset(start="hir.lower")
    context = _make_context(forms, "core-ast", session, options)
    return await pipeline.run_async(context)


async def compile_source_to_kind_async(
    source: str,
    session: PipelineSession,
    *,
    kind: str,
    options: PipelineOptions | None = None,
) -> PassResult:
    """从 source 起，跑到指定 artifact-kind 为止。.

    ``kind`` 必须是 ``ARTIFACT_KIND_TO_TARGET_PASS`` 中的键之一：cst / raw-forms /
    surface-forms / core-ast / hir / mir / lir / bytecode。
    """
    if kind not in ARTIFACT_KIND_TO_TARGET_PASS:
        raise ValueError(
            f"unknown artifact kind {kind!r}; valid kinds: {sorted(ARTIFACT_KIND_TO_TARGET_PASS)}"
        )
    end_pass = ARTIFACT_KIND_TO_TARGET_PASS[kind]
    pipeline = build_default_pipeline().subset(end=end_pass)
    context = _make_context(source, "source", session, options)
    return await pipeline.run_async(context)


def compile_source_to_kind(
    source: str,
    session: PipelineSession,
    *,
    kind: str,
    options: PipelineOptions | None = None,
) -> PassResult:
    """``compile_source_to_kind_async`` 的同步包装。."""
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


def bytecode_artifact(result: PassResult) -> BytecodeProgram:
    """从 PassResult 中取出 BytecodeProgram。.

    Pipeline 累计的 diagnostics 由调用端通过 ``result.diagnostics`` 自行处理；
    这里**不**合并到 ``BytecodeProgram.diagnostics`` —— BytecodeProgram 自带的
    诊断仅描述 bytecode 阶段自身的状态，由 ``evaluate_bytecode_async`` 负责抛出。
    """
    artifact = result.artifact
    if not isinstance(artifact, BytecodeProgram):
        raise TypeError(f"expected BytecodeProgram from pipeline, got {type(artifact).__name__}")
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


def core_ast_artifact(result: PassResult) -> CoreProgram:
    artifact = result.artifact
    if not isinstance(artifact, CoreProgram):
        raise TypeError(f"expected CoreProgram from pipeline, got {type(artifact).__name__}")
    return artifact


def raw_forms_artifact(result: PassResult) -> list:
    artifact = result.artifact
    if not isinstance(artifact, list):
        raise TypeError(f"expected raw-forms (list) from pipeline, got {type(artifact).__name__}")
    return artifact


def surface_forms_artifact(result: PassResult) -> list:
    artifact = result.artifact
    if not isinstance(artifact, list):
        raise TypeError(
            f"expected surface-forms (list) from pipeline, got {type(artifact).__name__}"
        )
    return artifact
