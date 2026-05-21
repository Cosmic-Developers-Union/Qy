import pytest

from qy.evaluator import ControlOperator
from qy.evaluator import EffectDefinition
from qy.evaluator import EffectOperator
from qy.evaluator import EvaluationError
from qy.evaluator import MetaOperator
from qy.evaluator import PureOperator
from qy.evaluator import ScopeOperator
from qy.evaluator import standard_environment
from qy.reader import Symbol
from qy.std import load_module

S = Symbol


def test_operator_kinds():
    env = standard_environment()

    for name in [
        "+",
        "-",
        "*",
        "/",
        "==",
        "atom",
        "eq",
        "is",
        "car",
        "cdr",
        "chain",
        "cons",
        "len",
        "get",
        "has?",
        "type",
    ]:
        assert isinstance(env.resolve(S(name)), PureOperator), f"{name} should be PureOperator"

    for name in ["let", "lambda", "defun", "defeffect", "module", "from"]:
        assert isinstance(env.resolve(S(name)), ScopeOperator), f"{name} should be ScopeOperator"

    for name in ["cond", "handle"]:
        assert isinstance(env.resolve(S(name)), ControlOperator), (
            f"{name} should be ControlOperator"
        )

    for name in [
        "print",
        "echo",
        "assert",
        "parallel",
        "cache",
        "perform",
        "resume",
    ]:
        assert isinstance(env.resolve(S(name)), EffectOperator), f"{name} should be EffectOperator"

    with pytest.raises(EvaluationError):
        env.resolve(S("py"))

    py_env = standard_environment()
    for sym, val in load_module("qy.py").exports.items():
        py_env.define(sym, val)
    assert isinstance(py_env.resolve(S("py")), EffectOperator)

    for name in ["quote", "eval", "macro"]:
        assert isinstance(env.resolve(S(name)), MetaOperator), f"{name} should be MetaOperator"

    for name in ["assert-failed", "python-error"]:
        effect = env.resolve(S(name))
        assert isinstance(effect, EffectDefinition), f"{name} should be EffectDefinition"
        assert not effect.resumable

    for name in ["set!", "set*", "setq"]:
        with pytest.raises(EvaluationError):
            env.resolve(S(name))
