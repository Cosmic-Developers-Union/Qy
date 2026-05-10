import unittest

from qy.analyzer import analyze_source
from qy.analyzer import type_check_source


class TestQyAnalyzer(unittest.TestCase):
    def test_analyze_valid_program(self):
        analysis = analyze_source("""
        (defun square (x) (* x x))
        (square 12)
        """)

        self.assertTrue(analysis.ok)
        self.assertEqual(analysis.diagnostics, [])

    def test_reports_reader_error(self):
        diagnostics = type_check_source("(+ 1")

        self.assertEqual(len(diagnostics), 1)
        self.assertEqual(diagnostics[0].severity, "error")
        self.assertIsNotNone(diagnostics[0].line)

    def test_reports_unresolved_symbol(self):
        diagnostics = type_check_source("(+ missing 1)")

        self.assertTrue(any("unresolved symbol 'missing'" in item.message for item in diagnostics))

    def test_reports_numeric_type_error(self):
        diagnostics = type_check_source("(+ true 1)")

        self.assertTrue(any("expects number arguments" in item.message for item in diagnostics))

    def test_let_scope_is_understood(self):
        self.assertEqual(type_check_source("(let ((x 1)) (+ x 2))"), [])
        self.assertTrue(type_check_source("(+ x 2)"))


if __name__ == "__main__":
    unittest.main()
