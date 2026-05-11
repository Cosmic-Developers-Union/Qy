import unittest

from qy.formatter import dump_program
from qy.formatter import format_source
from qy.reader import read


class TestQyFormatter(unittest.TestCase):
    def test_format_source_locks_simple_spacing(self):
        self.assertEqual(format_source("(+   1   2)"), "(+ 1 2)\n")

    def test_format_source_expands_nested_forms(self):
        self.assertEqual(
            format_source("(defun square (x) (* x x))"),
            "(defun\n  square\n  (x)\n  (* x x))\n",
        )

    def test_format_source_uses_quote_sugar(self):
        self.assertEqual(format_source("(quote abc)"), "'abc\n")

    def test_format_source_normalizes_tagged_literals(self):
        self.assertEqual(format_source('t"hello"'), "(t 'hello)\n")

    def test_format_source_preserves_dotted_pairs(self):
        self.assertEqual(format_source("(a . b)"), "(a . b)\n")

    def test_format_source_preserves_comments_and_blank_lines(self):
        self.assertEqual(
            format_source("; head\n\n(+  1 2) ; sum\n; tail\n"),
            "; head\n\n(+ 1 2)  ; sum\n; tail\n",
        )

    def test_format_source_aligns_trailing_comments(self):
        self.assertEqual(
            format_source("(+ 1 2) ; a\n(* 10 20) ; b\n"),
            "(+ 1 2)    ; a\n(* 10 20)  ; b\n",
        )

    def test_format_source_ignores_semicolon_inside_strings(self):
        self.assertEqual(format_source('(print "a;b") ; ok'), '(print "a;b")  ; ok\n')

    def test_dump_program_shows_ast(self):
        ast = dump_program(read("(+ 1 2)"))

        self.assertIn("Symbol('+')", ast)
        self.assertIn("Symbol('1')", ast)


if __name__ == "__main__":
    unittest.main()
