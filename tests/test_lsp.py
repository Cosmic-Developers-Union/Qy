import pytest

pytest.importorskip("pygls")

from lsprotocol import types

from qy.lsp import QyLanguageServer
from qy.lsp import completion_items
from qy.lsp import create_server
from qy.lsp import diagnostics_for_source
from qy.lsp import document_symbols_for_source
from qy.lsp import hover_for_source
from qy.lsp import signature_help_for_source


def test_diagnostics_for_valid_source():
    assert diagnostics_for_source("(+ 1 2)") == []


def test_diagnostics_for_syntax_error():
    diagnostics = diagnostics_for_source("(+ 1")

    assert len(diagnostics) == 1
    assert diagnostics[0].severity == types.DiagnosticSeverity.Error
    assert diagnostics[0].source == "qy"


def test_create_server():
    server = create_server()
    assert isinstance(server, QyLanguageServer)


def test_completion_items_include_builtins():
    labels = {item.label for item in completion_items()}

    assert "let" in labels
    assert "defun" in labels
    assert "defun form" in labels


def test_completion_items_include_document_symbols():
    labels = {item.label for item in completion_items("(defun local-add (a b) (+ a b))")}

    assert "local-add" in labels


def test_hover_for_builtin_operator():
    hover = hover_for_source("(let ((x 1)) x)", 0, 1)

    assert hover is not None
    assert isinstance(hover.contents, types.MarkupContent)


def test_document_symbols_for_source():
    symbols = document_symbols_for_source("(defun local-add (a b) (+ a b))")

    assert [symbol.name for symbol in symbols] == ["local-add"]


def test_signature_help_for_source():
    signature = signature_help_for_source("(defun square (x) (* x x))", 0, 7)

    assert signature is not None
    assert "defun" in signature.signatures[0].label
