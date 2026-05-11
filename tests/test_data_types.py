import pytest

from qy.errors import QyTypeError
from qy.evaluator import evaluate_source
from qy.reader import Symbol
from qy.values import QyChain
from qy.values import list_to_qy_cons

S = Symbol


def test_tuple():
    assert evaluate_source('(tuple 1 "two" true)') == (1, S("two"), True)
    assert evaluate_source("(tuple '(a b))") == (S("a"), S("b"))
    assert evaluate_source("(tuple? (tuple 'a 'b))")


def test_list():
    assert evaluate_source('(list 1 "two" true)') == [1, S("two"), True]
    assert evaluate_source("(list '(a b))") == [S("a"), S("b")]
    assert not evaluate_source("(list? '(a b))")
    assert evaluate_source("(list? (list 1 2))")


def test_dict():
    assert evaluate_source('(dict "name" "Qy" "items" (list 1 2))') == {
        S("name"): S("Qy"),
        S("items"): [1, 2],
    }
    assert evaluate_source('(dict? (dict "name" "Qy"))')
    assert evaluate_source("(dict '((name . Qy) (mode test)))") == {
        S("name"): S("Qy"),
        S("mode"): S("test"),
    }


def test_set():
    assert evaluate_source('(set "qy" "core" "qy")') == {S("qy"), S("core")}
    assert evaluate_source('(set? (set "qy"))')
    assert evaluate_source("(set '(a b a))") == {S("a"), S("b")}


def test_chain():
    assert evaluate_source("(chain (list 'a 'b))") == list_to_qy_cons([S("a"), S("b")])
    assert evaluate_source("(chain (tuple 'a 'b))") == list_to_qy_cons([S("a"), S("b")])


def test_len():
    assert evaluate_source("(len (list 1 2 3))") == 3
    assert evaluate_source("(len '(a b c))") == 3


def test_get():
    assert evaluate_source('(get (dict "name" "Qy") "name")') == S("Qy")
    assert evaluate_source('(get (list "a" "b") 1)') == S("b")
    assert evaluate_source("(get '(a b c) 1)") == S("b")
    assert evaluate_source('(get (dict "name" "Qy") "missing" "fallback")') == S("fallback")


def test_has():
    assert evaluate_source('(has? (set "core") "core")')
    assert evaluate_source('(has? (list "a" "b") 1)')


def test_list_car_cdr_cons():
    with pytest.raises(QyTypeError):
        evaluate_source('(car (list "a" "b"))')
    with pytest.raises(QyTypeError):
        evaluate_source('(cdr (list "a" "b" "c"))')
    assert evaluate_source('(cons \'a (list "b" "c"))') == QyChain(S("a"), [S("b"), S("c")])
