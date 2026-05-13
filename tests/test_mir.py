from typing import cast

import pytest

from qy import MIRBlock
from qy import MIRFunction
from qy import MIRInstruction
from qy import MIRProgram
from qy import MIRTerminator
from qy import compile_mir_bytecode
from qy import dump_mir
from qy import lower_mir
from qy import verify_mir
from qy.evaluator import standard_environment
from qy.ir import CallExpr
from qy.ir import CondExpr
from qy.ir import DefunExpr
from qy.lowering import lower_source
from qy.mir import MIROpcode
from qy.reader import Symbol


def test_mir_lowering_emits_cfg_blocks_for_cond():
    hir = lower_source("(cond (true 1) (false 2))")

    mir = lower_mir(hir)

    assert isinstance(mir, MIRProgram)
    assert mir.ok
    main = mir.functions[mir.main]
    assert len(main.blocks) > 1
    assert any(block.terminator.opcode == "BRANCH" for block in main.blocks)


def test_mir_lowering_preserves_tail_call_as_terminator():
    hir = lower_source(
        """
        (defun sum-to (n acc)
          (cond
            ((eq n 0) acc)
            (true (sum-to (- n 1) (+ acc n)))))
        """
    )
    definition = hir.body[0]
    assert isinstance(definition, DefunExpr)
    cond = definition.body[0]
    assert isinstance(cond, CondExpr)
    recursive_call = cond.clauses[1].result
    assert isinstance(recursive_call, CallExpr)
    assert recursive_call.tail_position

    mir = lower_mir(hir)
    sum_to = next(function for function in mir.functions if function.name.name == "sum-to")

    assert any(block.terminator.opcode == "TAIL_CALL" for block in sum_to.blocks)


def test_mir_lowering_keeps_top_level_results():
    hir = lower_source("(+ 1 2)\n(+ 3 4)")

    mir = lower_mir(hir)
    main = mir.functions[mir.main]

    assert (
        sum(
            1
            for block in main.blocks
            for instruction in block.instructions
            if instruction.opcode == "APPEND_RESULT"
        )
        == 2
    )


def test_mir_dump_formats_cfg_and_scope_information():
    hir = lower_source("(let ((x 1)) (cond (x (+ x 1)) (true 0)))")

    mir = lower_mir(hir)
    rendered = dump_mir(mir)

    assert "fn#0 <main>() entry=bb0 regs=" in rendered
    assert "ENTER_SCOPE" in rendered
    assert "EXIT_SCOPE" in rendered
    assert "BRANCH r" in rendered
    assert "APPEND_RESULT r" in rendered


def test_mir_dump_shows_lambda_and_macro_construction():
    hir = lower_source(
        """
        (let ((inc (lambda (x) (+ x 1))))
          (macro twice (form) (cons '+ (cons form (cons form '()))))
          inc)
        """
    )

    mir = lower_mir(hir)
    rendered = dump_mir(mir)

    assert "MAKE_FUNCTION fn#" in rendered
    assert "MAKE_MACRO twice" in rendered
    assert "STORE_LOCAL inc, r" in rendered
    assert "STORE_LOCAL twice, r" in rendered


def test_mir_lowering_lowers_component_definition_without_diagnostic():
    mir = lower_mir(lower_source("(component scale (x factor) (* x factor))"))

    assert mir.ok
    main = mir.functions[mir.main]
    assert any(
        instruction.opcode == "MAKE_FUNCTION"
        for block in main.blocks
        for instruction in block.instructions
    )
    assert any(
        instruction.opcode == "STORE_LOCAL" and instruction.operands[0] == Symbol("scale")
        for block in main.blocks
        for instruction in block.instructions
    )


def test_mir_dump_shows_tail_call_terminator():
    hir = lower_source(
        """
        (defun sum-to (n acc)
          (cond
            ((eq n 0) acc)
            (true (sum-to (- n 1) (+ acc n)))))
        """
    )

    mir = lower_mir(hir)
    rendered = dump_mir(mir)

    assert "TAIL_CALL r" in rendered


def test_verify_mir_accepts_lowered_program():
    mir = lower_mir(lower_source("(+ 1 2)"))

    assert verify_mir(mir) == ()


def test_verify_mir_reports_missing_jump_target():
    mir = MIRProgram(
        (
            MIRFunction(
                Symbol("broken"),
                (),
                1,
                (MIRBlock(0, (), MIRTerminator("JUMP", (99,))),),
                0,
            ),
        )
    )

    diagnostics = verify_mir(mir)

    assert any("jumps to missing block bb99" in item.message for item in diagnostics)


def test_verify_mir_reports_out_of_range_registers_and_invalid_tail_call_instruction():
    mir = MIRProgram(
        (
            MIRFunction(
                Symbol("broken"),
                (),
                1,
                (
                    MIRBlock(
                        0,
                        (
                            MIRInstruction(cast(MIROpcode, "TAIL_CALL"), (0, ()), None),
                            MIRInstruction("LOAD_CONST", (1, 42), None),
                        ),
                        MIRTerminator("RETURN", (1,)),
                    ),
                ),
                0,
            ),
        )
    )

    diagnostics = verify_mir(mir)

    assert any("TAIL_CALL as a non-terminator instruction" in item.message for item in diagnostics)
    assert any("out-of-range register r1" in item.message for item in diagnostics)


def test_compile_mir_bytecode_stops_on_verifier_errors():
    mir = MIRProgram(
        (
            MIRFunction(
                Symbol("broken"),
                (),
                1,
                (MIRBlock(0, (), MIRTerminator("JUMP", (99,))),),
                0,
            ),
        )
    )

    bytecode = compile_mir_bytecode(mir)

    assert not bytecode.ok
    assert bytecode.functions == ()
    assert any("jumps to missing block bb99" in item.message for item in bytecode.diagnostics)


def test_verify_mir_reports_malformed_operand_arity_instead_of_crashing():
    mir = MIRProgram(
        (
            MIRFunction(
                Symbol("broken"),
                (),
                1,
                (
                    MIRBlock(
                        0,
                        (MIRInstruction("CALL", (0,), None),),
                        MIRTerminator("BRANCH", (0, 1), None),
                    ),
                ),
                0,
            ),
        )
    )

    diagnostics = verify_mir(mir)

    assert any(
        "instruction 'CALL' expects 3 operands, got 1" in item.message for item in diagnostics
    )
    assert any(
        "terminator 'BRANCH' expects 3 operands, got 2" in item.message for item in diagnostics
    )


def test_verify_mir_reports_malformed_operand_kinds_instead_of_crashing():
    mir = MIRProgram(
        (
            MIRFunction(
                Symbol("broken"),
                (),
                1,
                (
                    MIRBlock(
                        0,
                        (MIRInstruction("CALL", (0, 0, "bad"), None),),
                        MIRTerminator("JUMP", ("bad",), None),
                    ),
                ),
                0,
            ),
        )
    )

    diagnostics = verify_mir(mir)

    assert any(
        "instruction 'CALL' expects a register tuple" in item.message for item in diagnostics
    )
    assert any("jumps to non-block target 'bad'" in item.message for item in diagnostics)


@pytest.mark.parametrize(
    ("source", "expected_expr"),
    (
        ('(assert false "bad")', "AssertExpr"),
        ("(eval '(+ 1 2))", "RuntimeEvalExpr"),
        ("(defeffect ask)", "DefeffectExpr"),
        ("(module demo (defun triple (x) (* x 3)))", "ModuleExpr"),
        ("(from qy.str import str-upper as upper)", "FromImportExpr"),
        ("(let () (defeffect ask) (perform ask 1))", "PerformExpr"),
        (
            "(let () (defeffect ask) (handle (perform ask 1) ((ask (arg k) arg))))",
            "HandleExpr",
        ),
        ("(resume k 1)", "ResumeExpr"),
    ),
)
def test_mir_lowering_reports_explicit_diagnostics_for_unsupported_hir_nodes(source, expected_expr):
    mir = lower_mir(lower_source(source))

    assert any(expected_expr in item.message for item in mir.diagnostics)
    main = mir.functions[mir.main]
    assert not any(
        instruction.opcode == "APPEND_RESULT"
        for block in main.blocks
        for instruction in block.instructions
    )


def test_mir_lowering_reports_runtime_meta_calls_explicitly():
    env = standard_environment()

    @env.register_meta("first-symbol")
    def first_symbol(expression, current_env):
        del current_env
        return expression[0]

    mir = lower_mir(lower_source("(first-symbol unknown)", env))

    assert any("RuntimeMetaCallExpr" in item.message for item in mir.diagnostics)
