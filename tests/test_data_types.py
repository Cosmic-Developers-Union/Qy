import pytest

from qy.core.syntax import list_to_chain
from qy.core.syntax import nil as QY_NIL
from qy.errors import QyTypeError
from qy.frontend.reader import Symbol
from qy.import_.registry import standard_bindings
from qy.runtime import evaluate_source
from qy.sem.core import DictValue
from qy.sem.core import ListValue
from qy.sem.core import SetValue
from qy.sem.core import T as QY_T
from qy.sem.core import TupleValue
from qy.session.runtime_space import RuntimeSpace as Environment

S = Symbol


def _py_env() -> Environment:
    return Environment(standard_bindings(("qy.core", "qy.io", "qy.py")))


def es(source: str) -> object:
    return evaluate_source(source, _py_env())


def test_tuple():
    result = es('(tuple 1 "two" true)')
    assert isinstance(result, TupleValue)
    assert result.items == (1, "two", QY_T)
    quoted = es("(tuple '(a b))")
    assert isinstance(quoted, TupleValue)
    assert quoted.items == (S("a"), S("b"))
    assert es("(tuple? (tuple 'a 'b))") is QY_T


def test_list():
    result = es('(list 1 "two" true)')
    assert isinstance(result, ListValue)
    assert result.items == (1, "two", QY_T)
    quoted = es("(list '(a b))")
    assert isinstance(quoted, ListValue)
    assert quoted.items == (S("a"), S("b"))
    assert es("(list? '(a b))") is QY_NIL
    assert es("(list? (list 1 2))") is QY_T


def test_dict():
    result = es('(dict "name" "Qy" "items" (list 1 2))')
    assert isinstance(result, DictValue)
    entries = dict(result.entries)
    assert entries["name"] == "Qy"
    assert isinstance(entries["items"], ListValue)
    assert entries["items"].items == (1, 2)
    assert es('(dict? (dict "name" "Qy"))') is QY_T
    quoted = es("(dict '((name . Qy) (mode test)))")
    assert isinstance(quoted, DictValue)
    assert quoted.entries == ((S("name"), S("Qy")), (S("mode"), S("test")))


def test_set():
    result = es('(set "qy" "core" "qy")')
    assert isinstance(result, SetValue)
    assert result.items == ("qy", "core")
    assert es('(set? (set "qy"))') is QY_T
    quoted = es("(set '(a b a))")
    assert isinstance(quoted, SetValue)
    assert quoted.items == (S("a"), S("b"))


def test_chain():
    assert es("(chain (list 'a 'b))") == list_to_chain([S("a"), S("b")])
    assert es("(chain (tuple 'a 'b))") == list_to_chain([S("a"), S("b")])


def test_len():
    assert es("(len (list 1 2 3))") == 3
    assert evaluate_source("(len '(a b c))") == 3


def test_get():
    assert es('(get (dict "name" "Qy") "name")') == "Qy"
    assert es('(get (list "a" "b") 1)') == "b"
    assert evaluate_source("(get '(a b c) 1)") == S("b")
    assert es('(get (dict "name" "Qy") "missing" "fallback")') == "fallback"


def test_has():
    assert es('(has? (set "core") "core")') is QY_T
    assert es('(has? (list "a" "b") 1)') is QY_T


def test_list_car_cdr_cons():
    with pytest.raises(QyTypeError):
        es('(car (list "a" "b"))')
    with pytest.raises(QyTypeError):
        es('(cdr (list "a" "b" "c"))')
    # cons 现在返回 Chain
    result = es('(cons \'a (list "b" "c"))')
    from qy.core.syntax import car
    from qy.core.syntax import cdr
    from qy.core.syntax import is_chain

    assert is_chain(result)
    assert car(result) == S("a")
    tail = cdr(result)
    assert isinstance(tail, ListValue)
    assert tail.items == ("b", "c")
