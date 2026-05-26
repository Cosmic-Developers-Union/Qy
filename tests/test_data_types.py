import pytest

from qy.core.syntax import list_to_chain
from qy.core.syntax import nil as QY_NIL
from qy.errors import QyTypeError
from qy.frontend.reader import Symbol
from qy.import_.registry import standard_bindings
from qy.runtime import evaluate_source
from qy.sem.core import T as QY_T
from qy.session.runtime_space import RuntimeSpace as Environment

S = Symbol


def _py_env() -> Environment:
    return Environment(standard_bindings(("qy.core", "qy.io", "qy.py")))


def es(source: str) -> object:
    return evaluate_source(source, _py_env())


def test_tuple():
    assert es('(tuple 1 "two" true)') == (1, "two", QY_T)
    assert es("(tuple '(a b))") == (S("a"), S("b"))
    assert es("(tuple? (tuple 'a 'b))") is QY_T


def test_list():
    assert es('(list 1 "two" true)') == [1, "two", QY_T]
    assert es("(list '(a b))") == [S("a"), S("b")]
    assert es("(list? '(a b))") is QY_NIL
    assert es("(list? (list 1 2))") is QY_T


def test_dict():
    assert es('(dict "name" "Qy" "items" (list 1 2))') == {
        "name": "Qy",
        "items": [1, 2],
    }
    assert es('(dict? (dict "name" "Qy"))') is QY_T
    assert es("(dict '((name . Qy) (mode test)))") == {
        S("name"): S("Qy"),
        S("mode"): S("test"),
    }


def test_set():
    assert es('(set "qy" "core" "qy")') == {"qy", "core"}
    assert es('(set? (set "qy"))') is QY_T
    assert es("(set '(a b a))") == {S("a"), S("b")}


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
    assert cdr(result) == ["b", "c"]
