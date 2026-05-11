from qy.analyzer import type_check_source


def test_let_scope_is_understood():
    assert type_check_source("(let ((x 1)) (+ x 2))") == []
    assert type_check_source("(+ x 2)")


def test_lambda_scope_is_understood():
    assert type_check_source("((lambda (x) (+ x 1)) 41)") == []


def test_component_scope_is_understood():
    assert (
        type_check_source("""
    (component scale (x factor) (* x factor))
    (scale 7 6)
    """)
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


def test_recursive_function_scope_is_understood():
    assert (
        type_check_source("""
    (defun countdown (n)
      (cond
        ((eq n 0) 0)
        (true (countdown (- n 1)))))
    """)
        == []
    )
