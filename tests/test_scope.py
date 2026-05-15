import pytest

from qy import Qy
from qy.evaluator import standard_environment
from qy.reader import Symbol

S = Symbol


def test_let_introduces_scope():
    qy = Qy()
    assert qy.evaluate_source("(let ((x 10) (y 20)) (+ x y))") == 30
    assert qy.evaluate_source("(let ((x 10)) x)") == 10


def test_let_can_override_literals_locally():
    assert Qy().evaluate_source("(let ((1 10)) (+ 1 2))") == 12


def test_lambda_creates_anonymous_function():
    assert Qy().evaluate_source("((lambda (x) (+ x 1)) 41)") == 42
    assert Qy().evaluate_source("(let ((inc (lambda (x) (+ x 1)))) (inc 41))") == 42


def test_defun_scope_operator():
    qy = Qy()
    qy.evaluate_source("(defun square (x) (* x x))")
    assert qy.evaluate_source("(square 12)") == 144


def test_defun_supports_multiple_body_forms():
    qy = Qy()
    qy.evaluate_source("(defun second (x y) x y)")
    assert qy.evaluate_source("(second 1 2)") == 2


def test_self_tail_recursive_function_uses_trampoline():
    assert (
        Qy().evaluate_source(
            """
            (let ()
              (defun sum-to (n acc)
                (cond
                  ((eq n 0) acc)
                  (true (sum-to (- n 1) (+ acc n)))))
              (sum-to 300 0))
            """
        )
        == 45150
    )


def test_component_defines_callable_component():
    from qy.stdlib import load_module

    env = standard_environment()
    for sym, val in load_module("qy.legacy").exports.items():
        env.define(sym, val)
    qy = Qy(env=env)
    qy.evaluate_source("(component scale (x factor) (* x factor))")
    assert qy.evaluate_source("(scale 7 6)") == 42


def test_define_operator_binds_in_env():
    q = Qy()
    result = q.evaluate_source("(define x 42)")
    assert result == 42
    assert q.evaluate_source("(+ x 1)") == 43


def test_duplicate_define_reports_error_at_lowering():
    from qy.lowering import lower_source

    result = lower_source("(define x 1) (define x 2)")
    assert any("'x' is already bound" in d.message for d in result.diagnostics)


def test_define_cannot_rebind_host_symbol_in_same_scope():
    from qy.lowering import lower_source

    result = lower_source("(define + 99)")
    assert any("'+' is already bound in this scope" in d.message for d in result.diagnostics)


def test_let_can_shadow_host_symbol_from_parent_scope():
    q = Qy()
    assert q.evaluate_source("(let ((+ 99)) +)") == 99


def test_qy_exposes_pre_symbol_space_chain():
    from qy.environment import Environment

    env = Environment()
    env.define(Symbol("x"), 1)
    qy = Qy(env=env.child())

    chain = qy.pre_symbol_space_chain

    assert len(chain) == 2
    assert chain[0].bindings[Symbol("x")] == 1
    assert Symbol("x") not in chain[1].bindings


def test_define_in_child_scope_can_shadow_parent_binding():
    q = Qy()
    q.evaluate_source("(define x 1)")
    assert q.evaluate_source("(let ((x 99)) x)") == 99
    assert q.evaluate_source("x") == 1


def test_define_once_raises_on_duplicate():
    from qy.environment import Environment
    from qy.errors import QyRuntimeError
    from qy.reader import Symbol

    env = Environment()
    env.define_once(Symbol("x"), 1)
    with pytest.raises(QyRuntimeError):
        env.define_once(Symbol("x"), 2)


def test_duplicate_defeffect_reports_error():
    from qy.lowering import lower_source

    result = lower_source("(defeffect ask) (defeffect ask)")
    assert any("'ask' is already bound" in d.message for d in result.diagnostics)


def test_define_once_opcode_enforced_at_runtime():
    from qy.bytecode import BytecodeFunction
    from qy.bytecode import BytecodeProgram
    from qy.bytecode import Instruction
    from qy.errors import QyRuntimeError
    from qy.register_vm import evaluate_bytecode

    fn = BytecodeFunction(
        name=Symbol("main"),
        params=(),
        register_count=2,
        instructions=(
            Instruction("LOAD_HOST", (0, 42), None),
            Instruction("DEFINE_ONCE", (Symbol("x"), 0), None),
            Instruction("LOAD_HOST", (1, 99), None),
            Instruction("DEFINE_ONCE", (Symbol("x"), 1), None),
            Instruction("RETURN", (0,), None),
        ),
    )
    program = BytecodeProgram(functions=(fn,), main=0)
    with pytest.raises(QyRuntimeError, match="already bound"):
        evaluate_bytecode(program)
