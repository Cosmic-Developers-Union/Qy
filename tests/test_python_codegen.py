from qy.lowering import lower_source
from qy.python_codegen import codegen_python


def _codegen(source: str) -> str:
    return codegen_python(lower_source(source))


def test_codegen_integer_literal():
    code = _codegen("42")
    assert "_result = 42" in code


def test_codegen_string_literal():
    code = _codegen('"hello"')
    assert "hello" in code


def test_codegen_arithmetic_addition():
    code = _codegen("(+ 1 2)")
    assert "(1 + 2)" in code


def test_codegen_arithmetic_multiplication():
    code = _codegen("(* 3 4)")
    assert "(3 * 4)" in code


def test_codegen_nested_arithmetic():
    code = _codegen("(+ (* 2 3) 4)")
    assert "(2 * 3)" in code
    assert "4" in code


def test_codegen_equality():
    code = _codegen("(eq 1 1)")
    assert "==" in code


def test_codegen_defun():
    code = _codegen("(defun double (x) (* x 2))")
    assert "def double(x):" in code
    assert "return" in code


def test_codegen_defun_with_call():
    code = _codegen("(defun add (a b) (+ a b))")
    assert "def add(a, b):" in code
    assert "(a + b)" in code


def test_codegen_cond_simple():
    code = _codegen("(cond (true 1) (false 2))")
    assert "1" in code


def test_codegen_cond_with_condition():
    code = _codegen("(cond ((eq 1 1) 42) (true 0))")
    assert "42" in code
    assert "==" in code


def test_codegen_let_binding():
    code = _codegen("(let ((x 10)) (+ x 1))")
    assert "lambda x:" in code
    assert "10" in code


def test_codegen_lambda():
    code = _codegen("(lambda (x) (* x x))")
    assert "lambda x:" in code
    assert "(x * x)" in code


def test_codegen_defun_kebab_name():
    code = _codegen("(defun my-func (x) x)")
    assert "def my_func(x):" in code


def test_codegen_macro_noop():
    code = _codegen("(macro double-it (x) (cons '* (cons x (cons x '()))))")
    assert "# macro" in code


def test_codegen_defeffect_comment():
    code = _codegen("(defeffect ask)")
    assert "# effect ask" in code


def test_codegen_symbol_true_false():
    code = _codegen("true")
    assert "True" in code
    code2 = _codegen("false")
    assert "False" in code2


def test_codegen_multi_defun_program():
    source = """
    (defun square (x) (* x x))
    (defun cube (x) (* x (square x)))
    (cube 3)
    """
    code = _codegen(source)
    assert "def square(x):" in code
    assert "def cube(x):" in code
    assert "_result" in code


def test_codegen_produces_valid_python():
    source = (
        "(defun fib (n) (cond ((eq n 0) 0) ((eq n 1) 1) (true (+ (fib (- n 1)) (fib (- n 2))))))"
    )
    code = _codegen(source)
    namespace: dict = {}
    exec(code, namespace)
    assert callable(namespace["fib"])
    assert namespace["fib"](10) == 55


def test_codegen_let_evaluates_correctly():
    code = _codegen("(let ((x 3) (y 4)) (+ x y))")
    namespace: dict = {}
    exec(f"_result = {code.split('_result = ', 1)[1].strip()}", namespace)
    assert namespace["_result"] == 7
