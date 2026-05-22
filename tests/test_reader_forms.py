import pytest

from qy.core.syntax import Chain
from qy.core.syntax import car
from qy.core.syntax import cdr
from qy.core.syntax import list_to_chain
from qy.frontend.reader import ReaderSyntaxError
from qy.frontend.reader import Symbol
from qy.frontend.reader import expand_surface_dialect
from qy.frontend.reader import get_span
from qy.frontend.reader import read
from qy.frontend.reader import read_one
from qy.frontend.reader import read_raw

S = Symbol


def L(*items, span=None):
    """测试辅助：构造 Chain."""
    return list_to_chain(list(items), span=span)


def test_raw_reader_keeps_surface_symbols():
    result = read_raw("'abc '(+ 1 2) ,x ,@xs")
    assert result == [
        S("'abc"),
        S("'"),
        L(S("+"), S("1"), S("2")),
        S(",x"),
        S(",@xs"),
    ]


def test_default_surface_keeps_comma_symbols_outside_quasiquote():
    result = read("(define , 10) (1 ,x) (, 1 2)")
    assert result == [
        L(S("define"), S(","), S("10")),
        L(S("1"), S(",x")),
        L(S(","), S("1"), S("2")),
    ]


def test_default_surface_expands_unquote_symbols_inside_quasiquote():
    result = read("(quasiquote (,x ,@xs , ,@))")
    assert result == [
        L(
            S("quasiquote"),
            L(
                L(S("unquote"), S("x")),
                L(S("unquote-splicing"), S("xs")),
                S(","),
                S(",@"),
            ),
        )
    ]


def test_define_target_is_not_surface_expanded():
    result = read("(define 'x 1) (define ' 2)")
    assert result == [
        L(S("define"), S("'x"), S("1")),
        L(S("define"), S("'"), S("2")),
    ]


def test_expand_surface_dialect_is_pure_function():
    raw = read_raw("'abc (+ 1 2)")
    result = expand_surface_dialect(raw)
    assert result == [L(S("quote"), S("abc")), L(S("+"), S("1"), S("2"))]


def test_dotted_pair_forms():
    form = read_one("(a . b)")

    # Improper list 现在是 Chain，不是 DottedTuple
    assert isinstance(form, Chain)
    assert car(form) == S("a")
    assert cdr(form) == S("b")
    # re-check readability
    form2 = read_one("(a . b)")
    assert isinstance(form2, Chain)


def test_invalid_dotted_pair_forms_are_rejected():
    with pytest.raises(ReaderSyntaxError):
        read_one("(. b)")


def test_forms_keep_source_spans():
    form = read_one("(+ 1\n 2)")
    assert isinstance(form, Chain)
    form_span = get_span(form)
    # 获取第三个元素（索引2）
    items = list(form)
    last_item_span = get_span(items[2])

    assert form_span is not None
    assert last_item_span is not None
    assert form_span.start_line == 1
    assert form_span.start_column == 1
    assert last_item_span.start_line == 2
    assert last_item_span.start_column == 2


def test_read_one_requires_exactly_one_form():
    with pytest.raises(ReaderSyntaxError):
        read_one("")
    with pytest.raises(ReaderSyntaxError):
        read_one("a b")
