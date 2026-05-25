import pytest

from qy.core.operators import ControlOperator
from qy.core.operators import MetaOperator
from qy.errors import QyRuntimeError
from qy.frontend.reader import Symbol
from qy.runtime import Qy
from qy.runtime import evaluate

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
    from qy.async_utils import run_coro
    from qy.passes.build import bytecode_artifact
    from qy.passes.build import compile_source_to_bytecode_async
    from qy.passes.build import compile_source_to_kind_async
    from qy.passes.build import core_ast_artifact
    from qy.passes.build import mir_artifact
    from qy.passes.pass_base import PipelineSession

    qy = Qy()
    source = """
    (macro twice (form) (cons '+ (cons form (cons form '()))))
    (twice 21)
    """

    session = PipelineSession(env=qy.env)
    expansion = run_coro(compile_source_to_kind_async(source, session, kind="core-ast"))
    program = core_ast_artifact(expansion)

    # macro 定义被过滤掉，只剩下展开后的宏调用
    assert len(program.forms) == 1
    expanded = program.forms[0]
    from qy.core.syntax import Chain
    from qy.core.syntax import car
    from qy.core.syntax import cdr
    from qy.core.syntax import chain_to_list

    assert isinstance(expanded, Chain)
    assert isinstance(car(expanded), Symbol)
    rest = chain_to_list(cdr(expanded))
    assert rest == [S("21"), S("21")]
    assert len(program.traces) == 1
    assert program.traces[0].renames[0].original == S("+")
    assert program.traces[0].renames[0].kind == "definition-site"
    first = car(expanded)
    assert isinstance(first, Symbol)
    assert first.name == program.traces[0].renames[0].rewritten.name

    mir_session = PipelineSession(env=qy.env)
    mir_result = run_coro(compile_source_to_kind_async(source, mir_session, kind="mir"))
    mir = mir_artifact(mir_result)

    bytecode_session = PipelineSession(env=qy.env)
    bytecode_result = run_coro(compile_source_to_bytecode_async(source, bytecode_session))
    bytecode = bytecode_artifact(bytecode_result)

    assert mir.ok
    assert bytecode.ok
    assert qy.evaluate_source(source) == 42
