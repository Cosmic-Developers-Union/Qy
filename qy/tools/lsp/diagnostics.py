# coding: utf-8

from __future__ import annotations

from lsprotocol import types

from qy.analysis import Diagnostic
from qy.analysis import analyze_source
from qy.async_utils import run_coro
from qy.passes.build import compile_source_to_kind_async
from qy.passes.pass_base import PipelineSession
from qy.runtime import Qy
from qy.tools.lsp.utils import shared_instance


def diagnostics_for_source(source: str, *, qy: Qy | None = None) -> list[types.Diagnostic]:
    runtime = qy or shared_instance()
    session = PipelineSession(env=runtime.env)
    expansion = run_coro(compile_source_to_kind_async(source, session, kind="core-ast"))
    diagnostics = list(expansion.diagnostics)
    if not any(d.severity == "error" for d in diagnostics):
        analysis = analyze_source(source, runtime.env)
        diagnostics.extend(analysis.diagnostics)
    return [diagnostic_to_lsp(diagnostic) for diagnostic in diagnostics]


def diagnostic_to_lsp(diagnostic: Diagnostic) -> types.Diagnostic:
    line = max((diagnostic.line or 1) - 1, 0)
    character = max((diagnostic.column or 1) - 1, 0)
    return types.Diagnostic(
        range=types.Range(
            start=types.Position(line=line, character=character),
            end=types.Position(line=line, character=character + 1),
        ),
        message=diagnostic.message,
        severity=severity_to_lsp(diagnostic.severity),
        source="qy",
    )


def severity_to_lsp(severity: str) -> types.DiagnosticSeverity:
    if severity == "warning":
        return types.DiagnosticSeverity.Warning
    if severity == "hint":
        return types.DiagnosticSeverity.Hint
    return types.DiagnosticSeverity.Error
