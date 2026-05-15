import pytest

from qy.errors import QyArityError
from qy.evaluator import ControlOperator
from qy.evaluator import PureOperator
from qy.operator_runtime import operator_uses_raw_args
from qy.operator_runtime import runtime_operator_semantics
from qy.operator_signature import Arity
from qy.operator_signature import OperatorSignature
from qy.runtime import Qy


def test_runtime_semantics_distinguish_eager_raw_and_custom_operators():
    eager = PureOperator("eager", lambda value: value)
    custom = PureOperator("custom", lambda value: value, argument_evaluator=lambda args, env: args)
    raw = ControlOperator("raw", lambda args, env: None)

    assert runtime_operator_semantics(eager).argument_mode == "eager"
    assert runtime_operator_semantics(custom).argument_mode == "custom"
    assert runtime_operator_semantics(raw).argument_mode == "raw"
    assert not operator_uses_raw_args(eager)
    assert operator_uses_raw_args(custom)
    assert operator_uses_raw_args(raw)


def test_vm_validates_declared_operator_arity_before_dispatch():
    qy = Qy()

    @qy.register_pure("pair", signature=OperatorSignature("tuple", Arity(2, 2)))
    def pair(left, right):
        return (left, right)

    with pytest.raises((QyArityError, Exception), match="pair expects exactly 2 arguments, got 1"):
        qy.evaluate_source("(pair 1)")
