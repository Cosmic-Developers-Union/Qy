from qy.evaluator import evaluate_source
from qy.evaluator import standard_environment
from qy.frontend.reader import Symbol
from qy.sem.core import CharValue
from qy.sem.core import IntValue
from qy.sem.core import StringValue
from qy.sem.core import T as QY_T
from qy.std import load_module

S = Symbol


def _str_env():
    env = standard_environment()
    for symbol, value in load_module("qy.str").exports.items():
        env.define(symbol, value)
    return env


def test_string_upper():
    assert evaluate_source('(string-upper "hello")', _str_env()) == StringValue("HELLO")


def test_string_lower():
    assert evaluate_source('(string-lower "HELLO")', _str_env()) == StringValue("hello")


def test_string_concat():
    assert evaluate_source('(string-concat "qy" "lang")', _str_env()) == StringValue("qylang")


def test_string_length():
    assert evaluate_source('(string-length "hello")', _str_env()) == IntValue(5)


def test_string_split():
    assert evaluate_source('(string-split "a,b,c" ",")', _str_env()) == (
        StringValue("a"),
        StringValue("b"),
        StringValue("c"),
    )


def test_string_replace():
    assert evaluate_source('(string-replace "hello" "l" "x")', _str_env()) == StringValue("hexxo")


def test_string_contains():
    assert evaluate_source('(string-contains? "hello" "ell")', _str_env()) is QY_T


def test_string_starts_with():
    assert evaluate_source('(string-starts-with? "hello" "he")', _str_env()) is QY_T


def test_string_ends_with():
    assert evaluate_source('(string-ends-with? "hello" "lo")', _str_env()) is QY_T


def test_string_at():
    assert evaluate_source('(string-at "hello" 1)', _str_env()) == CharValue("e")


def test_string_trim():
    assert evaluate_source('(string-trim "  hi  ")', _str_env()) == StringValue("hi")


def test_string_eq():
    assert evaluate_source('(string= "abc" "abc")', _str_env()) is QY_T
