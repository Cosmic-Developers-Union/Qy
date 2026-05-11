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

    def test_lambda_scope_is_understood(self):
        self.assertEqual(type_check_source("((lambda (x) (+ x 1)) 41)"), [])

    def test_component_scope_is_understood(self):
        diagnostics = type_check_source("""
        (component scale (x factor) (* x factor))
        (scale 7 6)
        """)

        self.assertEqual(diagnostics, [])

    def test_async_effect_operators_are_understood(self):
        self.assertEqual(type_check_source("(parallel (+ 1 2) (+ 3 4))"), [])
        self.assertEqual(type_check_source("(cache (+ 1 2))"), [])
        self.assertEqual(type_check_source("(await (spawn (+ 1 2)))"), [])
        self.assertEqual(type_check_source('(py "return a + b" :a 1 :b (+ 2 3))'), [])
        self.assertEqual(
            type_check_source(
                """
                (let ()
                  (defeffect ask)
                  (handle
                    (+ 1 (perform ask 41))
                    ((ask (arg k) (resume k arg)))))
                """
            ),
            [],
        )

    def test_reports_undeclared_perform_effect(self):
        diagnostics = type_check_source("(perform ask 41)")

        self.assertTrue(any("effect 'ask' is not declared" in item.message for item in diagnostics))

    def test_meta_operators_are_understood(self):
        self.assertEqual(type_check_source("(eval '(+ 1 2))"), [])
        self.assertEqual(type_check_source("(macro identity-form (form) form)"), [])
        self.assertEqual(
            type_check_source("""
            (macro identity-form (form) form)
            (identity-form (+ 1 2))
            """),
            [],
        )

    def test_import_alias_scope_is_understood(self):
        diagnostics = type_check_source("""
        (from qy.str import str-upper as upper)
        (upper "hello")
        """)

        self.assertEqual(diagnostics, [])

    def test_local_import_alias_scope_is_understood(self):
        diagnostics = type_check_source("""
        (let ()
          (from qy.str import str-upper as upper)
          (upper "hello"))
        """)

        self.assertEqual(diagnostics, [])

    def test_reports_unknown_imports(self):
        diagnostics = type_check_source("(from qy.str import missing as m)")

        self.assertTrue(any("has no export 'missing'" in item.message for item in diagnostics))

    def test_print_and_str_accept_text_symbols(self):
        self.assertEqual(type_check_source('(print "hello")'), [])
        self.assertEqual(type_check_source('(str-upper "hello")'), [])

    def test_recursive_function_scope_is_understood(self):
        diagnostics = type_check_source("""
        (defun countdown (n)
          (cond
            ((eq n 0) 0)
            (true (countdown (- n 1)))))
        """)

        self.assertEqual(diagnostics, [])


if __name__ == "__main__":
    unittest.main()
