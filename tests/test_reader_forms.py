import pytest

from qy.reader import DottedTuple
from qy.reader import ReaderSyntaxError
from qy.reader import Symbol
from qy.reader import expand_surface_dialect
from qy.reader import get_span
from qy.reader import read
from qy.reader import read_one
from qy.reader import read_raw

S = Symbol


def test_raw_reader_keeps_surface_symbols():
    assert read_raw("'abc '(+ 1 2) ,x ,@xs") == [
        S("'abc"),
        S("'"),
        (S("+"), S("1"), S("2")),
        S(",x"),
        S(",@xs"),
    ]


def test_default_surface_keeps_comma_symbols_outside_quasiquote():
    assert read("(define , 10) (1 ,x) (, 1 2)") == [
        (S("define"), S(","), S("10")),
        (S("1"), S(",x")),
        (S(","), S("1"), S("2")),
    ]


def test_default_surface_expands_unquote_symbols_inside_quasiquote():
    assert read("(quasiquote (,x ,@xs , ,@))") == [
        (
            S("quasiquote"),
            (
                (S("unquote"), S("x")),
                (S("unquote-splicing"), S("xs")),
                S(","),
                S(",@"),
            ),
        )
    ]


def test_define_target_is_not_surface_expanded():
    assert read("(define 'x 1) (define ' 2)") == [
        (S("define"), S("'x"), S("1")),
        (S("define"), S("'"), S("2")),
    ]


def test_expand_surface_dialect_is_pure_function():
    raw = read_raw("'abc (+ 1 2)")
    result = expand_surface_dialect(raw)
    assert result == [(S("quote"), S("abc")), (S("+"), S("1"), S("2"))]


def test_dotted_pair_forms():
    form = read_one("(a . b)")

    assert isinstance(form, DottedTuple)
    assert tuple(form) == (S("a"),)
    assert form.tail == S("b")
    assert read_one("(a . b)")  # re-check readability


def test_invalid_dotted_pair_forms_are_rejected():
    with pytest.raises(ReaderSyntaxError):
        read_one("(. b)")


def test_forms_keep_source_spans():
    form = read_one("(+ 1\n 2)")
    assert isinstance(form, tuple)
    form_span = get_span(form)
    last_item_span = get_span(form[2])

    assert form_span is not None
    assert last_item_span is not None
    assert form_span.line == 1
    assert form_span.column == 1
    assert last_item_span.line == 2
    assert last_item_span.column == 2


def test_read_one_requires_exactly_one_form():
    with pytest.raises(ReaderSyntaxError):
        read_one("")
    with pytest.raises(ReaderSyntaxError):
        read_one("a b")
