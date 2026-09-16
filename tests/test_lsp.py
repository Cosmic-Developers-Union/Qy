import pytest

pytest.importorskip("pygls")

from lsprotocol import types

from qy.tools.lsp import QyLanguageServer
from qy.tools.lsp import completion_items
from qy.tools.lsp import create_server
from qy.tools.lsp import definition_location
from qy.tools.lsp import diagnostics_for_source
from qy.tools.lsp import document_symbols_for_source
from qy.tools.lsp import hover_for_source
from qy.tools.lsp import reference_locations
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


def test_definition_location_points_to_local_binding():
    source = "(defun f (a) (+ a 1))\n(f 2)\n"

    location = definition_location(source, 1, 2, "file:///t.qy")

    assert location is not None
    assert location.uri == "file:///t.qy"
    assert location.range.start.line == 0
    assert location.range.start.character == 7


def test_reference_locations_lists_all_occurrences():
    source = "(defun f (a) (+ a 1))\n(f 2)\n"

    locations = reference_locations(source, 0, 10, "file:///t.qy")

    positions = {(item.range.start.line, item.range.start.character) for item in locations}
    assert (0, 10) in positions  # definition (parameter)
    assert (0, 16) in positions  # reference inside the body


def test_reference_locations_can_exclude_declaration():
    source = "(defun f (a) (+ a 1))\n(f 2)\n"

    locations = reference_locations(source, 0, 10, "file:///t.qy", include_declaration=False)

    positions = {(item.range.start.line, item.range.start.character) for item in locations}
    assert (0, 10) not in positions
    assert (0, 16) in positions


def test_navigation_server_registers_capabilities():
    from lsprotocol import types

    server = create_server()
    features = server.protocol.fm.features

    assert types.TEXT_DOCUMENT_DEFINITION in features
    assert types.TEXT_DOCUMENT_REFERENCES in features
