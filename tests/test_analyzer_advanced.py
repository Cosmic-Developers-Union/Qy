from qy.analyzer import type_check_source


def test_async_effect_operators_are_understood():
    assert type_check_source("(parallel (+ 1 2) (+ 3 4))") == []
    assert type_check_source("(cache (+ 1 2))") == []
    assert type_check_source("(await (spawn (+ 1 2)))") == []
    assert type_check_source('(assert true "ready")') == []
    assert type_check_source('(py "return a + b" :a 1 :b (+ 2 3))') == []
    assert (
        type_check_source(
            """
        (let ()
          (defeffect ask)
          (handle
            (+ 1 (perform ask 41))
            ((ask (arg k) (resume k arg)))))
        """
        )
        == []
    )
    assert (
        type_check_source(
            """
        (handle
          (assert false "missing title")
          ((assert-failed (err k) 'debugged)))
        """
        )
        == []
    )


def test_reports_undeclared_perform_effect():
    diagnostics = type_check_source("(perform ask 41)")

    assert any("effect 'ask' is not declared" in item.message for item in diagnostics)


def test_meta_operators_are_understood():
    assert type_check_source("(eval '(+ 1 2))") == []
    assert type_check_source("(macro identity-form (form) form)") == []
    assert type_check_source("(macro fresh () (gensym 'tmp))") == []
    assert (
        type_check_source("""
    (macro identity-form (form) form)
    (identity-form (+ 1 2))
    """)
        == []
    )


def test_tagged_literals_are_understood_as_operator_calls():
    assert (
        type_check_source("""
    (defun t (source) source)
    t"hello {name}"
    """)
        == []
    )


def test_print_and_str_accept_text_symbols():
    assert type_check_source('(print "hello")') == []
    assert type_check_source('(str-upper "hello")') == []


def test_legacy_data_operators_are_treated_as_non_core_calls():
    assert type_check_source('(tuple 1 "two" true)') == []
    assert type_check_source('(list 1 "two" true)') == []
    assert type_check_source('(dict "name" "Qy" "items" (list 1 2))') == []
    assert type_check_source('(set "qy" "core")') == []
    assert type_check_source('(get (dict "name" "Qy") "name")') == []
    assert type_check_source('(has? (set "core") "core")') == []
    assert type_check_source("(type '(a b c))") == []
    assert type_check_source("(== '(a b) '(a b))") == []
    assert type_check_source("(is '() none)") == []


def test_non_core_data_operator_arities_are_not_hard_coded():
    assert type_check_source('(dict "name")') == []
