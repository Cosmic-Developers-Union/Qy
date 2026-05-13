from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from qy.errors import EvaluationError
from qy.evaluator import PureOperator
from qy.evaluator import evaluate_source
from qy.evaluator import standard_environment
from qy.macro import MacroDefinition
from qy.reader import Symbol
from qy.stdlib import StandardModule
from qy.stdlib import register_module

S = Symbol


def test_module_defines_and_registers_exports():
    env = standard_environment()
    evaluate_source(
        """
        (module test.local
          (defun triple (x) (* x 3))
          (component scale (x factor) (* x factor))
          (exports triple scale))
        """,
        env,
    )
    evaluate_source("(from test.local import triple as t scale)", env)

    assert evaluate_source("(t 14)", env) == 42
    assert evaluate_source("(scale 7 6)", env) == 42


def test_from_import_as_operator():
    env = standard_environment()
    assert evaluate_source("(from qy.str import str-upper as upper)", env) is None
    assert evaluate_source('(upper "hello")', env) == S("HELLO")


def test_from_import_supports_multiple_imports():
    env = standard_environment()
    evaluate_source("(from qy.str import str-upper as upper str-lower as lower)", env)

    assert evaluate_source('(upper "qy")', env) == S("QY")
    assert evaluate_source('(lower "QY")', env) == S("qy")


def test_from_import_respects_local_scope():
    import pytest

    from qy.evaluator import EvaluationError

    env = standard_environment()
    assert evaluate_source(
        '(let () (from qy.str import str-upper as upper) (upper "qy"))', env
    ) == S("QY")
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
            (component scale (x factor) (* x factor))
            """,
            encoding="utf-8",
        )
        env = standard_environment()
        evaluate_source(f'(from "{path}" import triple as t scale)', env)

        assert evaluate_source("(t 14)", env) == 42
        assert evaluate_source("(scale 7 6)", env) == 42


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
