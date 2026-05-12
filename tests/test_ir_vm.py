import pytest

from qy import IRFunction
from qy import Qy
from qy import evaluate_ir_source
from qy.errors import QyEffectError
from qy.errors import QyEffectSignal
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


def test_qy_ir_backend_routes_evaluate_source_through_vm():
    qy = Qy(backend="ir")

    assert qy.evaluate_source("(let ((x 10) (y 32)) (+ x y))") == 42


def test_qy_ir_backend_evaluates_program_with_shared_scope():
    qy = Qy(backend="ir")

    assert qy.evaluate_program("(defun square (x) (* x x))\n(square 12)") == [
        qy.env.resolve(Symbol("square")),
        144,
    ]


async def test_ir_vm_perform_handle_resume_resumable_effect():
    qy = Qy()

    result = await qy.evaluate_ir_source_async(
        """
        (let ()
          (defeffect ask)
          (handle
            (+ 1 (perform ask 41))
            ((ask (arg k) (resume k arg)))))
        """
    )

    assert result == 42


async def test_ir_vm_handle_without_resume_behaves_like_catch():
    qy = Qy()

    result = await qy.evaluate_ir_source_async(
        """
        (let ()
          (defeffect fail)
          (handle
            (+ 1 (perform fail 41))
            ((fail (arg k) arg))))
        """
    )

    assert result == 41


async def test_ir_vm_resume_continues_body_after_perform():
    qy = Qy()

    result = await qy.evaluate_ir_source_async(
        """
        (let ()
          (defeffect ask)
          (handle
            (let ()
              (perform ask 1)
              42)
            ((ask (arg k) (resume k arg)))))
        """
    )

    assert result == 42


async def test_ir_vm_assert_failure_is_handleable():
    qy = Qy()

    result = await qy.evaluate_ir_source_async(
        """
        (handle
          (assert false "missing title")
          ((assert-failed (err k) 'debugged)))
        """
    )

    assert result == Symbol("debugged")


async def test_ir_vm_resume_rejects_non_resumable_assert_failure():
    qy = Qy()

    with pytest.raises(QyEffectError, match="not resumable"):
        await qy.evaluate_ir_source_async(
            """
            (handle
              (assert false "missing title")
              ((assert-failed (err k) (resume k true))))
            """
        )


async def test_ir_vm_unhandled_assert_failure_raises_signal():
    qy = Qy()

    with pytest.raises(QyEffectSignal) as exc_info:
        await qy.evaluate_ir_source_async('(assert false "missing title")')

    assert exc_info.value.effect == "assert-failed"
