import pytest

from qy.reader import DottedTuple
from qy.reader import ReaderSyntaxError
from qy.reader import Symbol
from qy.reader import get_span
from qy.reader import read
from qy.reader import read_one
from qy.reader import read_raw

S = Symbol


def test_list_and_quote_forms():
    assert read("'abc '(+ 1 2)") == [
        (S("quote"), S("abc")),
        (S("quote"), (S("+"), S("1"), S("2"))),
    ]


def test_quote_of_string_literal():
    # 字符串字面量作为 quote 参数需用显式 (quote ...) 形式
    assert read('(quote "abc")') == [(S("quote"), "abc")]


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


def test_dotted_pair_forms():
    form = read_one("(a . b)")

    assert isinstance(form, DottedTuple)
    assert tuple(form) == (S("a"),)
    assert form.tail == S("b")
    assert read_one("(a . b)")  # re-check readability


def test_invalid_dotted_pair_forms_are_rejected():
    with pytest.raises(ReaderSyntaxError):
        read_one("(. b)")


def test_let_binding_uses_bare_symbol_key():
    # 绑定名必须是裸 symbol；"abc" 现在是字符串字面量，末尾位置也是字符串
    assert read_one('(let ((abc 1)) abc "abc")') == (
        S("let"),
        ((S("abc"), S("1")),),
        S("abc"),
        "abc",
    )


def test_comments_are_ignored_outside_quoted_symbols():
    assert read('(+ 1 ; ignored\n 2) ";not comment"') == [
        (S("+"), S("1"), S("2")),
        ";not comment",
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
