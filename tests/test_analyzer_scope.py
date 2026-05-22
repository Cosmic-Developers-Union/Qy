from qy.analysis import type_check_source
from qy.evaluator import standard_environment
from qy.frontend.reader import Symbol
from qy.macro import MacroDefinition
from qy.std import StandardModule
from qy.std import register_module

S = Symbol


def test_let_scope_is_understood():
    assert type_check_source("(let ((x 1)) (+ x 2))") == []
    assert type_check_source("(+ x 2)")


def test_lambda_scope_is_understood():
    assert type_check_source("((lambda (x) (+ x 1)) 41)") == []


def test_defun_scope_is_understood():
    env = standard_environment()
    assert (
        type_check_source(
            """
    (defun scale (x factor) (* x factor))
    (scale 7 6)
    """,
            env,
        )
        == []
    )


def test_import_alias_scope_is_understood():
    assert (
        type_check_source("""
    (from qy.str import str-upper as upper)
    (upper "hello")
    """)
        == []
    )


def test_local_import_alias_scope_is_understood():
    assert (
        type_check_source("""
    (let ()
      (from qy.str import str-upper as upper)
      (upper "hello"))
    """)
        == []
    )


def test_reports_unknown_imports():
    diagnostics = type_check_source("(from qy.str import missing as m)")

    assert any("has no export 'missing'" in item.message for item in diagnostics)


def test_macro_only_import_alias_scope_is_understood():
    env = standard_environment()
    register_module(
        StandardModule(
            "review.macros",
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

    assert (
        type_check_source(
            """
        (from review.macros import const-answer)
        (const-answer)
        """,
            env,
        )
        == []
    )


def test_macro_capture_binding_is_understood_in_macro_body():
    assert (
        type_check_source(
            """
        (macro call-site-plus (value)
          (cons (capture '+) (cons value (cons 1 '()))))
        """
        )
        == []
    )


def test_same_source_unit_module_macro_import_scope_is_understood():
    assert (
        type_check_source(
            """
        (module review.inline.macros
          (macro const-answer () 42)
          (exports const-answer))
        (from review.inline.macros import const-answer)
        (const-answer)
        """
        )
        == []
    )


def test_recursive_function_scope_is_understood():
    assert (
        type_check_source("""
    (defun countdown (n)
      (cond
        ((= n 0) 0)
        (true (countdown (- n 1)))))
    """)
        == []
    )


def test_duplicate_define_reports_same_scope_error():
    diagnostics = type_check_source("(define x 1) (define x 2)")

    assert any("'x' is already bound in this scope" in item.message for item in diagnostics)


def test_define_cannot_rebind_host_symbol_in_same_scope():
    diagnostics = type_check_source("(define + 99)")
    assert any("'+' is already bound in this scope" in item.message for item in diagnostics)
