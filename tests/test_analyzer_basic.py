from qy.analyzer import analyze_source
from qy.analyzer import type_check_source


def test_analyze_valid_program():
    analysis = analyze_source("""
    (defun square (x) (* x x))
    (square 12)
    """)

    assert analysis.ok
    assert analysis.diagnostics == []


def test_reports_reader_error():
    diagnostics = type_check_source("(+ 1")

    assert len(diagnostics) == 1
    assert diagnostics[0].severity == "error"
    assert diagnostics[0].line is not None


def test_reports_unresolved_symbol():
    diagnostics = type_check_source("(+ missing 1)")

    assert any("unresolved symbol 'missing'" in item.message for item in diagnostics)


def test_reports_numeric_type_error():
    diagnostics = type_check_source("(+ true 1)")

    assert any("expects number arguments" in item.message for item in diagnostics)
