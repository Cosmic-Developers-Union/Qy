from qy.evaluator import evaluate_source
from qy.reader import Symbol

S = Symbol


def test_str_identity():
    assert evaluate_source('(str "hello")') == S("hello")


def test_str_upper():
    assert evaluate_source('(str-upper "hello")') == S("HELLO")


def test_str_lower():
    assert evaluate_source('(str-lower "HELLO")') == S("hello")


def test_str_concat():
    assert evaluate_source('(str-concat "qy" "lang")') == S("qylang")


def test_str_len():
    assert evaluate_source('(str-len "hello")') == 5


def test_str_split():
    assert evaluate_source('(str-split "a,b,c" ",")') == (S("a"), S("b"), S("c"))


def test_str_join():
    assert evaluate_source('(str-join "," \'(a b c))') == S("a,b,c")


def test_str_replace():
    assert evaluate_source('(str-replace "hello" "l" "x")') == S("hexxo")


def test_str_contains():
    assert evaluate_source('(str-contains? "hello" "ell")')


def test_str_starts_with():
    assert evaluate_source('(str-starts-with? "hello" "he")')


def test_str_ends_with():
    assert evaluate_source('(str-ends-with? "hello" "lo")')
