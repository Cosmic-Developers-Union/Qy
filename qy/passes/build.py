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

所有执行入口（``qy.runtime``、``qy.vm.instance.machine``、CLI）必须通过这个
工厂获取 Pipeline，禁止直接拼装 Pass 列表。

``compile_to`` 与 ``execute`` 是带诊断异常转换的高层包装，会在 Batch 3 接入
``qy.diag.raise``；当前先沿用各调用点既有的诊断处理逻辑，保持向后兼容。
"""

from __future__ import annotations

from qy.async_utils import run_coro
from qy.backend.vm.bytecode import BytecodeProgram
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
    "build_default_pipeline",
    "bytecode_artifact",
    "compile_core_forms_to_bytecode_async",
    "compile_forms_to_bytecode_async",
    "compile_source_to_bytecode",
    "compile_source_to_bytecode_async",
]


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
