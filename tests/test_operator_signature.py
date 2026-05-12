from qy.evaluator import EffectOperator
from qy.evaluator import MetaOperator
from qy.evaluator import PureOperator
from qy.operator_signature import Arity
from qy.operator_signature import EffectSpec
from qy.operator_signature import OperatorSignature
from qy.reader import Symbol
from qy.runtime import Qy

S = Symbol


def test_core_operators_expose_static_signatures():
    qy = Qy()

    plus = qy.env.resolve(S("+"))
    assert isinstance(plus, PureOperator)
    assert plus.signature == OperatorSignature("number", Arity())

    quote = qy.env.resolve(S("quote"))
    assert isinstance(quote, MetaOperator)
    assert quote.signature is not None
    assert quote.signature.compile_time
    assert quote.signature.argument_policy == ("raw",)

    assert_operator = qy.env.resolve(S("assert"))
    assert isinstance(assert_operator, EffectOperator)
    assert assert_operator.signature is not None
    assert assert_operator.signature.effects == (EffectSpec("assert-failed", resumable=False),)


def test_non_core_legacy_data_operators_do_not_have_core_signatures():
    qy = Qy()

    for name in ("list", "tuple", "dict", "set"):
        operator = qy.env.resolve(S(name))
        assert isinstance(operator, PureOperator)
        assert operator.signature is None


def test_custom_operator_can_declare_signature():
    qy = Qy()
    signature = OperatorSignature("number", Arity(1, 1))

    @qy.register_pure("triple", signature=signature)
    def triple(value):
        return value * 3

    operator = qy.env.resolve(S("triple"))
    assert isinstance(operator, PureOperator)
    assert operator.signature == signature
    assert qy.evaluate_source("(triple 14)") == 42
