from qy.core.operator_signature import Arity
from qy.core.operator_signature import EffectSpec
from qy.core.operator_signature import OperatorSignature
from qy.evaluator import EffectOperator
from qy.evaluator import MetaOperator
from qy.evaluator import PureOperator
from qy.frontend.reader import Symbol
from qy.runtime import Qy
from qy.std import STANDARD_PROFILE_MODULES
from qy.std import standard_profile_bindings

S = Symbol


def test_core_operators_expose_static_signatures():
    qy = Qy()

    plus = qy.env.resolve(S("+"))
    assert isinstance(plus, PureOperator)
    assert plus.signature == OperatorSignature("number", Arity(), rest_type="number")

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
    from qy.environment import Environment
    from qy.std import standard_bindings

    qy = Qy(env=Environment(standard_bindings(("qy.core", "qy.io", "qy.py"))))

    for name in ("list", "tuple", "dict", "set"):
        operator = qy.env.resolve(S(name))
        assert isinstance(operator, PureOperator)
        assert operator.signature is None


def test_default_core_exposes_python_container_helpers():
    qy = Qy()

    for name in ("list", "tuple", "dict", "set"):
        qy.env.resolve(S(name))


def test_default_profile_matches_standard_profile_bindings():
    qy = Qy()

    assert set(qy.env.bindings()) == set(standard_profile_bindings(STANDARD_PROFILE_MODULES))


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


def test_stdlib_signatures_subset_of_profile():
    """STDLIB_OPERATOR_SIGNATURES keys must be available in default profile."""
    from qy.core.operator_signature import STDLIB_OPERATOR_SIGNATURES

    qy = Qy()
    profile_keys = set(qy.env.bindings())
    for name in STDLIB_OPERATOR_SIGNATURES:
        assert Symbol(name) in profile_keys, (
            f"stdlib signature {name!r} not in default profile bindings"
        )


def test_truthy_has_standard_profile_signature():
    from qy.core.operator_signature import lookup_operator_signature

    signature = lookup_operator_signature("truthy")

    assert signature is not None
    assert signature.return_type == "bool"
    assert signature.arity == Arity(1, 1)


def test_collect_supported_operators_covers_profile():
    """collect_supported_operators lists all standard profile symbols."""
    from qy.std.profile import collect_supported_operators

    qy = Qy()
    supported_names: set[str] = set()
    for group in collect_supported_operators():
        for op in group.operators:
            supported_names.add(op.name)
    profile_names = {s.name for s in qy.env.bindings()}
    assert supported_names.issubset(profile_names), (
        f"supported operators not in profile: {supported_names - profile_names}"
    )
