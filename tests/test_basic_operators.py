from qy.evaluator import evaluate_source
from qy.reader import Symbol
from qy.values import QY_EMPTY_LIST
from qy.values import QY_NIL
from qy.values import QY_T
from qy.values import QyChain
from qy.values import list_to_qy_cons

S = Symbol


def test_quote():
    assert evaluate_source("'abc") == S("abc")


def test_atom():
    assert evaluate_source("(atom 'abc)")
    assert not evaluate_source("(atom '(abc def))")
    assert not evaluate_source("(atom '(abc . def))")
    assert evaluate_source("(atom '())")


def test_cond():
    assert evaluate_source("(cond (0 'truthy))") == S("truthy")
    assert evaluate_source("(cond (false 1) (true (+ 1 2)))") == 3


def test_eq():
    # eq is pure identity semantics
    assert not evaluate_source("(eq 'abc 'abc)")  # different Symbol objects
    assert not evaluate_source("(eq '(abc) '(abc))")  # different QyCons
    assert evaluate_source("(eq '() '())")  # both are QY_NIL singleton
    assert not evaluate_source("(eq '() none)")
    assert not evaluate_source("(== '() none)")
    assert evaluate_source("(eq nil '())")  # both are QY_NIL
    assert not evaluate_source("(eq none nil)")
    assert not evaluate_source("(eq T true)")
    assert not evaluate_source("(== T true)")


def test_is():
    assert evaluate_source("(== '(abc) '(abc))")
    assert not evaluate_source("(is '(abc) '(abc))")
    assert evaluate_source("(is '() '())")


def test_literals():
    assert evaluate_source("nil") is QY_NIL
    assert evaluate_source("T") is QY_T
    assert evaluate_source("none") is None


def test_type():
    assert evaluate_source("(type '(abc def))") == S("chain")
    assert evaluate_source("(type 'abc)") == S("symbol")
    assert evaluate_source("(type nil)") == S("nil")
    assert evaluate_source("(type T)") == S("T")
    assert evaluate_source("(type none)") == S("NoneType")


def test_car_cdr_cons():
    assert evaluate_source("(car nil)") is QY_NIL
    assert evaluate_source("(cdr nil)") is QY_NIL
    assert evaluate_source("(car '(abc def))") == S("abc")
    assert evaluate_source("(cdr '(abc def ghi))") == list_to_qy_cons([S("def"), S("ghi")])
    assert evaluate_source("(cons 'abc '(def ghi))") == list_to_qy_cons(
        [S("abc"), S("def"), S("ghi")]
    )
    assert evaluate_source("'()") is QY_EMPTY_LIST
    assert evaluate_source("'(abc . def)") == QyChain(S("abc"), S("def"))


def test_apply_uses_runtime_literals_for_quoted_args():
    assert evaluate_source("(apply + (quote (1 2 3)))") == 6


def test_quasiquote_unquote_splicing_works_without_internal_helpers():
    value = evaluate_source("(quasiquote (a (unquote-splicing (quote (b c))) d))")
    assert value == list_to_qy_cons([S("a"), S("b"), S("c"), S("d")])
