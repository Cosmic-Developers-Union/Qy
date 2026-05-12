from qy import BytecodeProgram
from qy import Qy
from qy import compile_bytecode
from qy.lowering import lower_source


def test_bytecode_compiler_emits_program_for_core_call():
    program = lower_source("(+ 1 2)")
    bytecode = compile_bytecode(program)

    assert isinstance(bytecode, BytecodeProgram)
    assert bytecode.ok
    assert bytecode.functions
    assert bytecode.functions[bytecode.main].instructions


def test_register_vm_evaluates_arithmetic_and_let():
    qy = Qy(backend="bytecode")

    assert qy.evaluate_source("(+ 1 2 3)") == 6
    assert qy.evaluate_source("(let ((x 10) (y 32)) (+ x y))") == 42


def test_register_vm_defun_can_be_called_across_steps():
    qy = Qy(backend="bytecode")

    qy.evaluate_source("(defun square (x) (* x x))")

    assert qy.evaluate_source("(square 12)") == 144


def test_register_vm_tail_recursion_uses_frame_replacement():
    qy = Qy(backend="bytecode")

    result = qy.evaluate_source(
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


def test_register_vm_runs_after_macroexpand():
    qy = Qy(backend="bytecode")
    qy.evaluate_source("(macro twice (form) (cons '+ (cons form (cons form '()))))")

    assert qy.evaluate_source("(twice (+ 1 2))") == 6


def test_register_vm_evaluate_program_returns_each_top_level_result():
    qy = Qy(backend="bytecode")

    assert qy.evaluate_program("(+ 1 2)\n(+ 3 4)") == [3, 7]
