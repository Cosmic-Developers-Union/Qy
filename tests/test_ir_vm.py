from qy import IRFunction
from qy import Qy
from qy import evaluate_ir_source
from qy.evaluator import standard_environment
from qy.reader import Symbol


def test_ir_vm_evaluates_core_calls_and_let():
    assert evaluate_ir_source("(let ((x 10) (y 20)) (+ x y))") == 30


def test_ir_vm_defun_can_be_called_across_repl_steps():
    qy = Qy()

    function = qy.evaluate_ir_source("(defun square (x) (* x x))")

    assert isinstance(function, IRFunction)
    assert qy.evaluate_ir_source("(square 12)") == 144


def test_ir_vm_lambda_call():
    assert evaluate_ir_source("((lambda (x) (+ x 1)) 41)") == 42


def test_ir_vm_self_tail_recursion_uses_virtual_stack():
    result = evaluate_ir_source(
        """
        (let ()
          (defun sum-to (n acc)
            (cond
              ((eq n 0) acc)
              (true (sum-to (- n 1) (+ acc n)))))
          (sum-to 2000 0))
        """
    )

    assert result == 2001000


def test_ir_vm_mutual_tail_recursion_uses_virtual_stack():
    result = evaluate_ir_source(
        """
        (let ()
          (defun even (n)
            (cond
              ((eq n 0) true)
              (true (odd (- n 1)))))
          (defun odd (n)
            (cond
              ((eq n 0) false)
              (true (even (- n 1)))))
          (even 1501))
        """
    )

    assert result is False


def test_ir_vm_function_is_visible_to_lowering_after_definition():
    qy = Qy()
    qy.evaluate_ir_source("(defun identity (x) x)")

    program = qy.lower_source("(identity 42)")

    assert program.ok
    assert qy.evaluate_ir(program) == 42


def test_ir_vm_can_resolve_runtime_environment_bindings():
    env = standard_environment()
    env.define(Symbol("answer"), 42)

    assert evaluate_ir_source("answer", env) == 42
