import pytest

from qy.reader import DottedTuple
from qy.reader import ReaderSyntaxError
from qy.reader import Symbol
from qy.reader import get_span
from qy.reader import read
from qy.reader import read_one

S = Symbol


def test_list_and_quote_forms():
    assert read("'abc '\"abc\" '(+ 1 2)") == [
        (S("quote"), S("abc")),
        (S("quote"), S("abc")),
        (S("quote"), (S("+"), S("1"), S("2"))),
    ]


def test_dotted_pair_forms():
    form = read_one("(a . b)")

    assert isinstance(form, DottedTuple)
    assert tuple(form) == (S("a"),)
    assert form.tail == S("b")
    assert read_one("(a . b)")  # re-check readability


def test_invalid_dotted_pair_forms_are_rejected():
    with pytest.raises(ReaderSyntaxError):
        read_one("(. b)")


def test_let_binding_symbols_can_be_written_with_quotes():
    assert read_one('(let (("abc" 1)) abc "abc")') == (
        S("let"),
        ((S("abc"), S("1")),),
        S("abc"),
        S("abc"),
    )


def test_comments_are_ignored_outside_quoted_symbols():
    assert read('(+ 1 ; ignored\n 2) ";not comment"') == [
        (S("+"), S("1"), S("2")),
        S(";not comment"),
    ]


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
