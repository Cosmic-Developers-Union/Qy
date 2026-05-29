import pytest

from qy import BytecodeProgram
from qy import Qy
from qy.async_utils import run_coro
from qy.build.pipeline import bytecode_artifact
from qy.build.pipeline import compile_source_to_bytecode_async
from qy.errors import EvaluationError
from qy.frontend.reader import Symbol
from qy.passes.pass_base import PipelineSession


def test_bytecode_compiler_emits_program_for_core_call():
    session = PipelineSession()
    result = run_coro(compile_source_to_bytecode_async("(+ 1 2)", session))
    bytecode = bytecode_artifact(result)

    assert isinstance(bytecode, BytecodeProgram)
    assert bytecode.ok
    assert bytecode.functions
    assert bytecode.functions[bytecode.main].instructions


def test_register_vm_evaluates_arithmetic_and_let():
    qy = Qy()

    assert qy.evaluate_source("(+ 1 2 3)") == 6
    assert qy.evaluate_source("(let ((x 10) (y 32)) (+ x y))") == 42


def test_register_vm_defun_can_be_called_across_steps():
    qy = Qy()

    qy.evaluate_source("(defun square (x) (* x x))")

    assert qy.evaluate_source("(square 12)") == 144


def test_register_vm_tail_recursion_uses_frame_replacement():
    qy = Qy()

    result = qy.evaluate_source(
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


def test_register_vm_runs_after_macroexpand():
    qy = Qy()

    assert qy.evaluate_source("(macro twice (form) (cons '+ (cons form (cons form '()))))") is None
    with pytest.raises(EvaluationError):
        qy.env.resolve(Symbol("twice"))

    assert qy.evaluate_source("(twice (+ 1 2))") == 6


def test_register_vm_preserves_macro_hygiene_and_explicit_capture():
    qy = Qy()

    assert (
        qy.evaluate_source(
            """
                        (macro with-temp (expr)
                            (cons 'let
                                (cons
                                    (cons (cons 'tmp (cons 1 '())) '())
                                    (cons expr '()))))
                        (macro add-one (value)
                            (cons '+ (cons value (cons 1 '()))))
                        (macro call-site-plus (value)
                            (cons (capture '+) (cons value (cons 1 '()))))
                        """
        )
        is None
    )

    assert qy.evaluate_source("(let ((tmp 99)) (with-temp tmp))") == 99
    assert qy.evaluate_source("(let ((+ (lambda (a b) 0))) (add-one 41))") == 42
    assert qy.evaluate_source("(let ((+ (lambda (a b) 0))) (call-site-plus 41))") == 0


def test_register_vm_evaluate_program_returns_each_top_level_result():
    qy = Qy()

    assert qy.evaluate_program("(+ 1 2)\n(+ 3 4)") == [3, 7]
