import pytest

from qy import Qy
from qy.errors import QyEffectError
from qy.errors import QyEffectSignal
from qy.errors import QyTypeError
from qy.evaluator import standard_environment
from qy.reader import Symbol
from qy.values import QY_NIL


def test_vm_evaluates_core_calls_and_let():
    assert Qy().evaluate_source("(let ((x 10) (y 20)) (+ x y))") == 30


def test_vm_defun_can_be_called_across_repl_steps():
    qy = Qy()

    qy.evaluate_source("(defun square (x) (* x x))")

    assert qy.evaluate_source("(square 12)") == 144


def test_vm_lambda_call():
    assert Qy().evaluate_source("((lambda (x) (+ x 1)) 41)") == 42


def test_vm_self_tail_recursion():
    result = Qy().evaluate_source(
        """
        (let ()
          (defun sum-to (n acc)
            (cond
              ((= n 0) acc)
              (true (sum-to (- n 1) (+ acc n)))))
          (sum-to 2000 0))
        """
    )

    assert result == 2001000


def test_vm_mutual_tail_recursion():
    result = Qy().evaluate_source(
        """
        (let ()
          (defun even (n)
            (cond
              ((= n 0) true)
              (true (odd (- n 1)))))
          (defun odd (n)
            (cond
              ((= n 0) false)
              (true (even (- n 1)))))
          (even 1501))
        """
    )

    assert result is QY_NIL


def test_vm_runtime_errors_include_virtual_stack_frames():
    qy = Qy()

    with pytest.raises(QyTypeError) as exc_info:
        qy.evaluate_source(
            """
            (let ()
              (defun bad (x) (car x))
              (defun outer () (+ (bad 1) 1))
              (outer))
            """
        )

    assert [frame.name for frame in exc_info.value.frames if frame.name is not None] == [
        "outer",
        "bad",
    ]


def test_vm_function_is_visible_to_lowering_after_definition():
    qy = Qy()
    qy.evaluate_source("(defun identity (x) x)")

    program = qy.lower_source("(identity 42)")

    assert program.ok
    assert qy.evaluate_source("(identity 42)") == 42


def test_vm_can_resolve_runtime_environment_bindings():
    env = standard_environment()
    env.define(Symbol("answer"), 42)

    assert Qy(env=env).evaluate_source("answer") == 42


def test_qy_evaluate_source_routes_through_register_vm():
    qy = Qy()

    assert qy.evaluate_source("(let ((x 10) (y 32)) (+ x y))") == 42


def test_qy_evaluate_program_with_shared_scope():
    qy = Qy()

    result = qy.evaluate_program("(defun square (x) (* x x))\n(square 12)")
    assert len(result) == 2
    assert result[1] == 144


async def test_vm_perform_handle_resume_resumable_effect():
    qy = Qy()

    result = await qy.evaluate_source_async(
        """
        (let ()
          (defeffect ask)
          (handle
            (+ 1 (perform ask 41))
            ((ask (arg k) (resume k arg)))))
        """
    )

    assert result == 42


async def test_vm_handle_without_resume_behaves_like_catch():
    qy = Qy()

    result = await qy.evaluate_source_async(
        """
        (let ()
          (defeffect fail)
          (handle
            (+ 1 (perform fail 41))
            ((fail (arg k) arg))))
        """
    )

    assert result == 41


async def test_vm_resume_continues_body_after_perform():
    qy = Qy()

    result = await qy.evaluate_source_async(
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


async def test_vm_assert_failure_is_handleable():
    qy = Qy()

    result = await qy.evaluate_source_async(
        """
        (handle
          (assert false "missing title")
          ((assert-failed (err k) 'debugged)))
        """
    )

    assert result == Symbol("debugged")


async def test_vm_resume_rejects_non_resumable_assert_failure():
    qy = Qy()

    with pytest.raises(QyEffectError, match="not resumable"):
        await qy.evaluate_source_async(
            """
            (handle
              (assert false "missing title")
              ((assert-failed (err k) (resume k true))))
            """
        )


async def test_vm_unhandled_assert_failure_raises_signal():
    qy = Qy()

    with pytest.raises(QyEffectSignal) as exc_info:
        await qy.evaluate_source_async('(assert false "missing title")')

    assert exc_info.value.effect == "assert-failed"
