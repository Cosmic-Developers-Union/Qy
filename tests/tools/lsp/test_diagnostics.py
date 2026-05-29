# coding: utf-8

from lsprotocol import types

from qy.diag import Diagnostic
from qy.source import SourceSpan
from qy.tools.lsp.diagnostics import diagnostic_to_lsp
from qy.tools.lsp.diagnostics import diagnostics_for_source
from qy.tools.lsp.diagnostics import severity_to_lsp


def test_severity_to_lsp():
    assert severity_to_lsp("error") == types.DiagnosticSeverity.Error
    assert severity_to_lsp("warning") == types.DiagnosticSeverity.Warning
    assert severity_to_lsp("hint") == types.DiagnosticSeverity.Hint


def test_diagnostic_to_lsp_uses_span_range():
    diagnostic = Diagnostic(
        "oops",
        span=SourceSpan("test.qy", 2, 3, 4, 5),
    )
    lsp_diagnostic = diagnostic_to_lsp(diagnostic)

    assert lsp_diagnostic.range.start.line == 1
    assert lsp_diagnostic.range.start.character == 2
    assert lsp_diagnostic.range.end.line == 3
    assert lsp_diagnostic.range.end.character == 4

    source = "(defun hello () (+ 1 2))"
    diagnostics = diagnostics_for_source(source)
    assert isinstance(diagnostics, list)


def test_diagnostics_for_source_invalid():
    source = "(defun)"
    diagnostics = diagnostics_for_source(source)
    assert len(diagnostics) > 0
    assert all(isinstance(d, types.Diagnostic) for d in diagnostics)
