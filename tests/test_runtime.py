import pytest

from qy.errors import QyRuntimeError
from qy.evaluator import ControlOperator
from qy.evaluator import MetaOperator
from qy.evaluator import evaluate
from qy.frontend.reader import Symbol
from qy.runtime import Qy

S = Symbol


def test_qy_instance_registers_external_operators():
    qy = Qy()

    @qy.register_pure("double")
    def double(value):
        return value * 2

    @qy.register_control("unless")
    def unless(args, env):
        condition, result = args
        if evaluate(condition, env):
            return None
        return evaluate(result, env)

    @qy.register_meta("first-symbol")
    def first_symbol(expression, env):
        del env
        return expression[0]

    assert qy.evaluate_source("(double 21)") == 42
    assert qy.evaluate_source("(unless false 7)") == 7
    with pytest.raises(
        QyRuntimeError, match="meta operator 'first-symbol' can only run during macro expansion"
    ):
        qy.evaluate_source("(first-symbol unknown)")


def test_legacy_operator_registration_names():
    qy = Qy()

    @qy.register_evaluation("unless")
    def unless(args, env):
        condition, result = args
        if evaluate(condition, env):
            return None
        return evaluate(result, env)

    @qy.register_syntax("first-symbol")
    def first_symbol(expression, env):
        del env
        return expression[0]

    assert isinstance(qy.env.resolve(S("unless")), ControlOperator)
    assert isinstance(qy.env.resolve(S("first-symbol")), MetaOperator)
    assert qy.evaluate_source("(unless false 7)") == 7
    with pytest.raises(
        QyRuntimeError, match="meta operator 'first-symbol' can only run during macro expansion"
    ):
        qy.evaluate_source("(first-symbol unknown)")


def test_qy_instance_exposes_pipeline_helpers():
    qy = Qy()

    expansion = qy.macroexpand_source(
        """
        (macro twice (form) (cons '+ (cons form (cons form '()))))
        (twice 21)
        """
    )

    assert expansion.ok
    # macro 定义被过滤掉，只剩下展开后的宏调用
    assert len(expansion.forms) == 1
    expanded = expansion.forms[0]
    from qy.core.syntax import Chain
    from qy.core.syntax import car
    from qy.core.syntax import cdr
    from qy.core.syntax import chain_to_list

    assert isinstance(expanded, Chain)
    assert isinstance(car(expanded), Symbol)
    rest = chain_to_list(cdr(expanded))
    assert rest == [S("21"), S("21")]
    assert len(expansion.traces) == 1
    assert expansion.traces[0].renames[0].original == S("+")
    assert expansion.traces[0].renames[0].kind == "definition-site"
    first = car(expanded)
    assert isinstance(first, Symbol)
    assert first.name == expansion.traces[0].renames[0].rewritten.name

    program = qy.lower(expansion.forms)
    mir = qy.lower_mir(program)
    bytecode = qy.compile_mir_bytecode(mir)

    assert mir.ok
    assert bytecode.ok
    assert qy.evaluate_bytecode(bytecode) == 42
