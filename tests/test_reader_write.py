from typing import cast

from qy.core.syntax import Chain
from qy.core.syntax import Form
from qy.core.syntax import Symbol as _Symbol
from qy.core.syntax import car
from qy.core.syntax import cdr
from qy.core.syntax import chain_to_list
from qy.core.syntax import is_chain
from qy.core.syntax import is_nil
from qy.core.syntax import list_to_chain
from qy.frontend.reader import read
from qy.frontend.reader import read_one
from qy.frontend.reader import write
from qy.frontend.reader import write_program

S = _Symbol


def L(*items: object, tail: Form | None = None) -> Form:
    return list_to_chain(list(items), tail=tail)


def test_read_raw_ast_is_symbol_and_chain_only():
    forms = read('(load "my docs") (+ 1 2)')

    assert len(forms) == 2
    first, second = forms
    assert isinstance(first, Chain)
    assert chain_to_list(first)[0] == S("load")
    assert isinstance(second, Chain)
    assert [cast(_Symbol, item).name for item in chain_to_list(second)] == ["+", "1", "2"]


def test_read_one_returns_chain():
    form = read_one('(let (("abc" 1)) abc "abc")')

    assert is_chain(form)
    items = chain_to_list(form)
    assert items[0] == S("let")
    assert is_chain(items[1])


def test_improper_chain_is_dotted_pair():
    form = read_one("(a . b)")

    assert is_chain(form)
    assert car(form) == S("a")
    assert cdr(form) == S("b")
    assert not is_nil(cdr(form))


def test_write_qy_form():
    assert write(S("abc")) == "abc"
    assert write(S("hello world")) == '"hello world"'
    assert write(S("(not a list)")) == '"(not a list)"'
    assert write(S("hello\nworld")) == r'"hello\nworld"'
    assert write(L(S("+"), S("1"), S("2"))) == "(+ 1 2)"
    assert write(S('"hello"')) == '"hello"'
    assert write(S('"hello world"')) == '"hello world"'


def test_write_dotted_pair():
    assert write(L(S("a"), S("b"), tail=S("c"))) == "(a b . c)"


def test_write_program():
    forms: list[Form] = [S("abc"), L(S("+"), S("1"), S("2"))]

    assert write_program(forms) == "abc\n(+ 1 2)"


def test_string_literal_write():
    assert write(S('"abc"')) == '"abc"'
    assert write(S('"hello world"')) == '"hello world"'
