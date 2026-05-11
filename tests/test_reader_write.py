import pytest

from qy.reader import Symbol
from qy.reader import form_to_tuple
from qy.reader import read_one_tuple
from qy.reader import read_tuple
from qy.reader import tuple_to_form
from qy.reader import write
from qy.reader import write_program
from qy.reader import write_tuple
from qy.reader import write_tuple_program

S = Symbol


def test_code_to_tuple_exchange_form():
    assert read_tuple('(load "my docs") (+ 1 2)') == [
        (S("load"), S("my docs")),
        (S("+"), S("1"), S("2")),
    ]
    assert read_one_tuple('(let (("abc" 1)) abc "abc")') == (
        S("let"),
        ((S("abc"), S("1")),),
        S("abc"),
        S("abc"),
    )


def test_tuple_exchange_form_to_qy_form():
    exchange_form = (S("embed"), (S("load"), S("docs")), S(":model"), S("text-embedding"))
    qy_form = (S("embed"), (S("load"), S("docs")), S(":model"), S("text-embedding"))

    assert tuple_to_form(exchange_form) == qy_form
    assert form_to_tuple(qy_form) == exchange_form


def test_write_qy_form():
    assert write(S("abc")) == "abc"
    assert write(S("hello world")) == '"hello world"'
    assert write(S("(not a list)")) == '"(not a list)"'
    assert write(S("hello\nworld")) == r'"hello\nworld"'
    assert write((S("+"), S("1"), S("2"))) == "(+ 1 2)"


def test_write_tuple_exchange_form():
    source = write_tuple((S("embed"), (S("load"), S("my docs")), S(":size"), 800))

    assert source == '(embed (load "my docs") :size 800)'
    assert read_one_tuple(source) == (S("embed"), (S("load"), S("my docs")), S(":size"), S("800"))


def test_write_programs():
    qy_forms = [S("abc"), (S("+"), S("1"), S("2"))]
    tuple_forms = [S("abc"), (S("+"), 1, 2)]

    assert write_program(qy_forms) == "abc\n(+ 1 2)"
    assert write_tuple_program(tuple_forms) == "abc\n(+ 1 2)"
    assert read_tuple(write_tuple_program(tuple_forms)) == qy_forms


def test_python_string_tuple_atom_is_literal_not_symbol():
    with pytest.raises(TypeError):
        tuple_to_form("abc")
    with pytest.raises(TypeError):
        write_tuple("abc")
