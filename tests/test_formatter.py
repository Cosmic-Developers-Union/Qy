from qy.reader import read
from qy.tools.fmt import dump_program
from qy.tools.fmt import format_source


def test_format_source_locks_simple_spacing():
    assert format_source("(+   1   2)") == "(+ 1 2)\n"


def test_format_source_expands_nested_forms():
    assert format_source("(defun square (x) (* x x))") == "(defun square (x) (* x x))\n"


def test_format_source_uses_quote_sugar():
    assert format_source("(quote abc)") == "'abc\n"


def test_format_source_normalizes_tagged_literals():
    assert format_source('t"hello"') == '(t \'"hello")\n'


def test_format_source_preserves_dotted_pairs():
    assert format_source("(a . b)") == "(a . b)\n"


def test_format_source_preserves_comments_and_blank_lines():
    assert (
        format_source("; head\n\n(+  1 2) ; sum\n; tail\n") == "; head\n\n(+ 1 2)  ; sum\n; tail\n"
    )


def test_format_source_aligns_trailing_comments():
    assert format_source("(+ 1 2) ; a\n(* 10 20) ; b\n") == "(+ 1 2)    ; a\n(* 10 20)  ; b\n"


def test_format_source_ignores_semicolon_inside_strings():
    assert format_source('(print "a;b") ; ok') == '(print "a;b")  ; ok\n'


def test_dump_program_shows_ast():
    ast = dump_program(read("(+ 1 2)"))

    assert "Symbol('+')" in ast
    assert "Symbol('1')" in ast
