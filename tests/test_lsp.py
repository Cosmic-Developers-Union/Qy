import pytest

pytest.importorskip("pygls")

from lsprotocol import types

from qy.tools.lsp import QyLanguageServer
from qy.tools.lsp import completion_items
from qy.tools.lsp import create_server
from qy.tools.lsp import diagnostics_for_source
from qy.tools.lsp import document_symbols_for_source
from qy.tools.lsp import hover_for_source
from qy.tools.lsp import signature_help_for_source


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


def test_completion_includes_local_bindings_from_hir():
    source = "(defun f (alpha) (let ((beta 1)) (+ alpha beta)))"

    labels = {item.label for item in completion_items(source, 0, 0)}

    assert "alpha" in labels
    assert "beta" in labels


def test_hover_reports_local_binding():
    source = "(defun f (alpha) (+ alpha 1))"

    hover = hover_for_source(source, 0, 12)

    assert hover is not None
    contents = hover.contents
    assert isinstance(contents, types.MarkupContent)
    assert "local binding" in contents.value
    assert "alpha" in contents.value


def test_document_locals_reads_canonical_hir_facts():
    from qy.tools.lsp.facts import document_locals

    source = """
    (defeffect ask)
    (defun f (a)
      (let ((b 1)) (define c 2))
      (handle (perform ask 1) ((ask (v k) (resume k v)))))
    """

    facts = {(binding.name, binding.source) for binding in document_locals(source)}

    assert ("a", "lambda-param") in facts
    assert ("b", "let-binding") in facts
    assert ("c", "define") in facts
    assert ("ask", "defeffect") in facts
    assert ("k", "handler-continuation") in facts
