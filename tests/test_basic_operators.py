from qy.core.syntax import Chain
from qy.core.syntax import list_to_chain
from qy.core.syntax import nil as QY_EMPTY_LIST
from qy.core.syntax import nil as QY_NIL
from qy.frontend.reader import Symbol
from qy.runtime import evaluate_source
from qy.sem.core import NONE as QY_NONE
from qy.sem.core import T as QY_T

S = Symbol


def test_quote():
    assert evaluate_source("'abc") == S("abc")


def test_atom():
    assert evaluate_source("(atom 'abc)") is QY_T
    assert evaluate_source("(atom '(abc def))") is QY_NIL
    assert evaluate_source("(atom '(abc . def))") is QY_NIL
    assert evaluate_source("(atom '())") is QY_T


def test_cond():
    assert evaluate_source("(cond (0 'truthy))") == S("truthy")
    # false is now QY_NIL (nil-only truth), so first clause is skipped
    assert evaluate_source("(cond (false 1) (true (+ 1 2)))") == 3


def test_truthy():
    assert evaluate_source("(truthy 1)") is QY_T
    assert evaluate_source("(truthy none)") is QY_NIL
    assert evaluate_source("(truthy '())") is QY_NIL


def test_eq():
    # eq: value equality for atoms (symbol/number/string), identity for chains
    assert evaluate_source("(eq 'abc 'abc)") is QY_T  # same symbol name -> equal
    assert evaluate_source("(eq '(abc) '(abc))") is QY_NIL  # different QyCons
    assert evaluate_source("(eq '() '())") is QY_T  # both are QY_NIL singleton
    assert evaluate_source("(eq '() none)") is QY_NIL
    assert evaluate_source("(== '() none)") is QY_NIL
    assert evaluate_source("(eq nil '())") is QY_T  # both are QY_NIL
    assert evaluate_source("(eq none nil)") is QY_NIL
    assert evaluate_source("(eq T true)") is QY_T  # both resolve to QY_T
    assert evaluate_source("(== T true)") is QY_T  # both resolve to QY_T


def test_is():
    assert evaluate_source("(== '(abc) '(abc))") is QY_T
    assert evaluate_source("(is '(abc) '(abc))") is QY_NIL
    assert evaluate_source("(is '() '())") is QY_T


def test_literals():
    assert evaluate_source("nil") is QY_NIL
    assert evaluate_source("T") is QY_T
    assert evaluate_source("none") is QY_NONE


def test_type():
    assert evaluate_source("(type '(abc def))") == S("chain")
    assert evaluate_source("(type 'abc)") == S("symbol")
    assert evaluate_source("(type nil)") == S("nil")
    assert evaluate_source("(type T)") == S("T")
    assert evaluate_source("(type none)") == S("none")


def test_car_cdr_cons():
    assert evaluate_source("(car nil)") is QY_NIL
    assert evaluate_source("(cdr nil)") is QY_NIL
    assert evaluate_source("(car '(abc def))") == S("abc")
    assert evaluate_source("(cdr '(abc def ghi))") == list_to_chain([S("def"), S("ghi")])
    assert evaluate_source("(cons 'abc '(def ghi))") == list_to_chain(
        [S("abc"), S("def"), S("ghi")]
    )
    assert evaluate_source("'()") is QY_EMPTY_LIST
    assert evaluate_source("'(abc . def)") == Chain(S("abc"), S("def"))


def test_apply_uses_runtime_literals_for_quoted_args():
    assert evaluate_source("(apply + (quote (1 2 3)))") == 6


def test_quasiquote_unquote_splicing_works_without_internal_helpers():
    value = evaluate_source("(quasiquote (a (unquote-splicing (quote (b c))) d))")
    assert value == list_to_chain([S("a"), S("b"), S("c"), S("d")])
