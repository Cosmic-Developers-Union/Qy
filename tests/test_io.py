from contextlib import redirect_stdout
from io import StringIO

import pytest

from qy.evaluator import EvaluationError
from qy.evaluator import evaluate
from qy.evaluator import evaluate_source
from qy.evaluator import standard_environment
from qy.frontend.reader import Symbol

S = Symbol


def test_print_and_echo():
    env = standard_environment()
    output = StringIO()

    with redirect_stdout(output):
        result = evaluate_source('(print "hello" (+ 1 2))', env)
        echo_result = evaluate_source('(echo "done")', env)

    assert result == 3
    assert echo_result == "done"
    assert output.getvalue().splitlines() == ["hello 3", "done"]
    with pytest.raises(EvaluationError):
        evaluate(S("hello"), env)


def test_tagged_literal_calls_user_operator():
    from qy.std import load_module

    env = standard_environment()
    for sym, val in load_module("qy.str").exports.items():
        env.define(sym, val)
    evaluate_source('(defun t (source) (string-concat "template:" source))', env)

    from qy.sem.core import StringValue

    assert evaluate_source('t"hello {name}"', env) == StringValue("template:hello {name}")
