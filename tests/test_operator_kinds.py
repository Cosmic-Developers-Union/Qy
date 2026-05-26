import pytest

from qy.core.operators import ControlOperator
from qy.core.operators import EffectOperator
from qy.core.operators import MetaOperator
from qy.core.operators import PureOperator
from qy.core.operators import ScopeOperator
from qy.errors import EvaluationError
from qy.frontend.reader import Symbol
from qy.import_.registry import load_module
from qy.sem.runtime import EffectDefinition
from qy.session.runtime_space import create_standard_runtime_space as standard_environment

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
