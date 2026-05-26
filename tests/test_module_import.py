from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from qy.core.operators import PureOperator
from qy.errors import EvaluationError
from qy.frontend.reader import Symbol
from qy.import_.module import StandardModule
from qy.import_.registry import register_module
from qy.macro import MacroDefinition
from qy.runtime import evaluate_source
from qy.sem.core import StringValue
from qy.session.runtime_space import create_standard_runtime_space as standard_environment

S = Symbol


def test_module_defines_and_registers_exports():
    env = standard_environment()
    evaluate_source(
        """
        (module test.local
          (defun triple (x) (* x 3))
                    (defun scale (x factor) (* x factor))
          (exports triple scale))
        """,
        env,
    )
    evaluate_source("(from test.local import triple as t scale)", env)

    assert evaluate_source("(t 14)", env) == 42
    assert evaluate_source("(scale 7 6)", env) == 42


def test_from_import_as_operator():
    env = standard_environment()
    assert evaluate_source("(from qy.str import string-upper as upper)", env) is None

    assert evaluate_source('(upper "hello")', env) == StringValue("HELLO")


def test_from_import_supports_multiple_imports():
    env = standard_environment()
    evaluate_source("(from qy.str import string-upper as upper string-lower as lower)", env)

    assert evaluate_source('(upper "qy")', env) == StringValue("QY")
    assert evaluate_source('(lower "QY")', env) == StringValue("qy")


def test_from_import_respects_local_scope():
    import pytest

    from qy.errors import EvaluationError

    env = standard_environment()
    assert evaluate_source(
        '(let () (from qy.str import string-upper as upper) (upper "qy"))', env
    ) == StringValue("QY")
    with pytest.raises(EvaluationError):
        evaluate_source('(upper "qy")', env)


def test_from_import_supports_registered_modules():
    register_module(
        StandardModule(
            "test.math",
            {S("triple"): PureOperator("triple", lambda value: value * 3)},
        )
    )
    env = standard_environment()
    evaluate_source("(from test.math import triple as t)", env)

    assert evaluate_source("(t 14)", env) == 42


def test_from_import_cannot_override_existing_binding():
    env = standard_environment()
    env.define(S("upper"), 42)

    with pytest.raises(EvaluationError, match="already bound in this scope"):
        evaluate_source("(from qy.str import string-upper as upper)", env)


def test_from_import_supports_compile_time_macro_exports():
    env = standard_environment()
    register_module(
        StandardModule(
            "test.macros",
            {},
            {
                S("const-answer"): MacroDefinition(
                    S("const-answer"),
                    (),
                    (42,),
                    env,
                )
            },
        )
    )

    assert evaluate_source("(from test.macros import const-answer)\n(const-answer)", env) == 42
    with pytest.raises(EvaluationError):
        env.resolve(S("const-answer"))


def test_from_import_supports_same_source_unit_module_definition():
    env = standard_environment()

    assert (
        evaluate_source(
            """
            (module test.inline
              (defun triple (x) (* x 3))
              (exports triple))
            (from test.inline import triple as t)
            (t 14)
            """,
            env,
        )
        == 42
    )


def test_from_import_supports_same_source_unit_module_macro_exports():
    env = standard_environment()

    assert (
        evaluate_source(
            """
            (module test.inline.macros
              (macro const-answer () 42)
              (exports const-answer))
            (from test.inline.macros import const-answer)
            (const-answer)
            """,
            env,
        )
        == 42
    )
    with pytest.raises(EvaluationError):
        env.resolve(S("const-answer"))


def test_from_import_supports_qy_files():
    with TemporaryDirectory() as temp_dir:
        path = Path(temp_dir) / "math_ops.qy"
        path.write_text(
            """
            (defun triple (x) (* x 3))
            (defun scale (x factor) (* x factor))
            """,
            encoding="utf-8",
        )
        env = standard_environment()
        evaluate_source(f'(from "{path}" import triple as t scale)', env)

        assert evaluate_source("(t 14)", env) == 42
        assert evaluate_source("(scale 7 6)", env) == 42


def test_module_macro_can_reference_module_local_helper():
    """F1: exported macro can reference unexported module-local helper."""
    env = standard_environment()
    result = evaluate_source(
        """
        (module review.localmacro
          (defun helper (x) (+ x 1))
          (macro call-helper (value)
            (cons 'helper (cons value '())))
          (exports call-helper))
        (from review.localmacro import call-helper)
        (call-helper 41)
        """,
        env,
    )
    assert result == 42


def test_from_import_supports_python_files():
    with TemporaryDirectory() as temp_dir:
        path = Path(temp_dir) / "math_ops.py"
        path.write_text(
            """
def triple(value):
    return value * 3

def plus_one(value):
    return value + 1
""",
            encoding="utf-8",
        )
        env = standard_environment()
        evaluate_source(f'(from "{path}" import triple as t plus-one)', env)

        assert evaluate_source("(t 14)", env) == 42
        assert evaluate_source("(plus-one 41)", env) == 42
