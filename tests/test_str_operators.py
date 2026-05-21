from qy.evaluator import evaluate_source
from qy.evaluator import standard_environment
from qy.reader import Symbol
from qy.std import load_module

S = Symbol


def _str_env():
    env = standard_environment()
    for symbol, value in load_module("qy.str").exports.items():
        env.define(symbol, value)
    return env


def test_str_identity():
    assert evaluate_source('(str "hello")', _str_env()) == S("hello")


def test_str_upper():
    assert evaluate_source('(str-upper "hello")', _str_env()) == S("HELLO")


def test_str_lower():
    assert evaluate_source('(str-lower "HELLO")', _str_env()) == S("hello")


def test_str_concat():
    assert evaluate_source('(str-concat "qy" "lang")', _str_env()) == S("qylang")


def test_str_len():
    assert evaluate_source('(str-len "hello")', _str_env()) == 5


def test_str_split():
    assert evaluate_source('(str-split "a,b,c" ",")', _str_env()) == (S("a"), S("b"), S("c"))


def test_str_join():
    assert evaluate_source('(str-join "," \'(a b c))', _str_env()) == S("a,b,c")


def test_str_replace():
    assert evaluate_source('(str-replace "hello" "l" "x")', _str_env()) == S("hexxo")


def test_str_contains():
    assert evaluate_source('(str-contains? "hello" "ell")', _str_env())


def test_str_starts_with():
    assert evaluate_source('(str-starts-with? "hello" "he")', _str_env())


def test_str_ends_with():
    assert evaluate_source('(str-ends-with? "hello" "lo")', _str_env())
