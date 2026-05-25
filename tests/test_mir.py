from typing import cast

from qy import MIRBlock
from qy import MIRFunction
from qy import MIRInstruction
from qy import MIRProgram
from qy import MIRTerminator
from qy import dump_mir
from qy import verify_mir
from qy.backend.vm.compiler import compile_lir_bytecode
from qy.frontend.reader import Symbol
from qy.ir import CallExpr
from qy.ir import CondExpr
from qy.ir import DefineExpr
from qy.ir import LambdaExpr
from qy.ir.mir import MIROpcode
from qy.passes.hir.lower import lower_source
from qy.passes.lir.lower import lower_lir
from qy.passes.mir.normalize import lower_mir


def compile_mir_bytecode(mir):
    return compile_lir_bytecode(lower_lir(mir))


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
            ((= n 0) acc)
            (true (sum-to (- n 1) (+ acc n)))))
        """
    )
    definition = hir.body[0]
    assert isinstance(definition, DefineExpr)
    assert isinstance(definition.value, LambdaExpr)
    cond = definition.value.body[0]
    assert isinstance(cond, CondExpr)
    recursive_call = cond.clauses[1].result
    assert isinstance(recursive_call, CallExpr)
    assert recursive_call.tail_position

    mir = lower_mir(hir)

    assert any(
        block.terminator.opcode == "TAIL_CALL"
        for function in mir.functions
        for block in function.blocks
    )


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
    assert "DEFINE_ONCE twice, r" in rendered


def test_mir_lowering_lowers_defun_definition_without_diagnostic():
    mir = lower_mir(lower_source("(defun scale (x factor) (* x factor))"))

    assert mir.ok
    main = mir.functions[mir.main]
    assert any(
        instruction.opcode == "MAKE_FUNCTION"
        for block in main.blocks
        for instruction in block.instructions
    )
    assert any(
        instruction.opcode == "DEFINE_ONCE" and instruction.operands[0] == Symbol("scale")
        for block in main.blocks
        for instruction in block.instructions
    )


def test_mir_dump_shows_tail_call_terminator():
    hir = lower_source(
        """
        (defun sum-to (n acc)
          (cond
            ((= n 0) acc)
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
                            MIRInstruction("LOAD_HOST", (1, 42), None),
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


def test_mir_lowering_assert_emits_branch_and_raise_effect():
    mir = lower_mir(lower_source('(assert false "bad")'))

    assert mir.ok
    main = mir.functions[mir.main]
    assert any(block.terminator.opcode == "BRANCH" for block in main.blocks)
    assert any(block.terminator.opcode == "RAISE_EFFECT" for block in main.blocks)


def test_mir_dump_shows_raise_effect_for_assert():
    mir = lower_mir(lower_source('(assert false "bad")'))
    rendered = dump_mir(mir)

    assert "RAISE_EFFECT" in rendered
    assert "assert-failed" in rendered


def test_bytecode_vm_assert_passes_when_condition_is_true():
    from qy.sem.core import T as QY_T
    from qy.vm.instance.machine import evaluate_bytecode_source

    result = evaluate_bytecode_source("(assert true)")

    assert result is QY_T


def test_bytecode_vm_assert_raises_effect_signal_when_condition_is_false():
    import pytest as _pytest

    from qy.errors import QyEffectSignal
    from qy.vm.instance.machine import evaluate_bytecode_source

    with _pytest.raises(QyEffectSignal) as exc_info:
        evaluate_bytecode_source('(assert false "expected failure")')

    assert exc_info.value.args[0] == "assert-failed" or "assert-failed" in str(exc_info.value)


def test_mir_verify_accepts_raise_effect_terminator():
    mir = lower_mir(lower_source("(assert true)"))
    diagnostics = verify_mir(mir)

    # No errors; warnings from def-use analysis are acceptable
    errors = [d for d in diagnostics if d.severity == "error"]
    assert errors == []


def test_mir_lowering_runtime_eval_emits_runtime_eval_instruction():
    mir = lower_mir(lower_source("(eval '(+ 1 2))"))

    assert mir.ok
    main = mir.functions[mir.main]
    assert any(
        instruction.opcode == "RUNTIME_EVAL"
        for block in main.blocks
        for instruction in block.instructions
    )


def test_mir_dump_shows_runtime_eval_instruction():
    mir = lower_mir(lower_source("(eval '(+ 1 2))"))
    rendered = dump_mir(mir)

    assert "RUNTIME_EVAL" in rendered


def test_bytecode_vm_runtime_eval_evaluates_quoted_form():
    from qy.vm.instance.machine import evaluate_bytecode_source

    result = evaluate_bytecode_source("(eval '(+ 1 2))")

    assert result == 3


def test_mir_lowering_module_emits_define_module_instruction():
    mir = lower_mir(lower_source("(module demo (defun triple (x) (* x 3)))"))

    assert mir.ok
    main = mir.functions[mir.main]
    assert any(
        instruction.opcode == "DEFINE_MODULE"
        for block in main.blocks
        for instruction in block.instructions
    )


def test_mir_dump_shows_define_module_and_from_import():
    mir = lower_mir(
        lower_source("(module demo (defun triple (x) (* x 3)))\n(from demo import triple)")
    )
    rendered = dump_mir(mir)

    assert "DEFINE_MODULE" in rendered
    assert "FROM_IMPORT" in rendered


def test_bytecode_vm_module_and_from_import_work_end_to_end():
    from qy.vm.instance.machine import evaluate_bytecode_source

    result = evaluate_bytecode_source(
        "(module math.helpers (defun double (x) (* x 2)))\n"
        "(from math.helpers import double)\n"
        "(double 21)"
    )

    assert result == 42


def test_mir_lowering_defeffect_emits_defeffect_instruction():
    mir = lower_mir(lower_source("(defeffect ask)"))

    assert mir.ok
    main = mir.functions[mir.main]
    assert any(
        instruction.opcode == "DEFEFFECT"
        for block in main.blocks
        for instruction in block.instructions
    )


def test_mir_dump_shows_defeffect_perform_handle_resume():
    mir = lower_mir(
        lower_source(
            "(defeffect ask)\n(handle (perform ask 1) ((ask (arg k) (resume k (* arg 2)))))"
        )
    )
    rendered = dump_mir(mir)

    assert "DEFEFFECT" in rendered
    assert "PERFORM" in rendered
    assert "HANDLE" in rendered
    assert "RESUME" in rendered


def test_bytecode_vm_defeffect_defines_effect_in_env():
    import asyncio

    from qy.sem.runtime import EffectDefinition
    from qy.session.runtime_space import create_standard_runtime_space as standard_environment
    from qy.vm.instance.machine import evaluate_bytecode_source_async

    env = standard_environment()
    asyncio.run(evaluate_bytecode_source_async("(defeffect my-signal)", env))

    assert isinstance(env.resolve(Symbol("my-signal")), EffectDefinition)


def test_bytecode_vm_handle_returns_body_result_when_no_effect():
    from qy.vm.instance.machine import evaluate_bytecode_source

    result = evaluate_bytecode_source("(defeffect ask)\n(handle 42 ((ask (arg k) 0)))")

    assert result == 42


def test_bytecode_vm_handle_routes_to_handler_on_perform():
    from qy.vm.instance.machine import evaluate_bytecode_source

    result = evaluate_bytecode_source(
        "(defeffect ask)\n(handle (perform ask 99) ((ask (arg k) arg)))"
    )

    assert result == 99


def test_bytecode_vm_resume_continues_computation():
    from qy.vm.instance.machine import evaluate_bytecode_source

    result = evaluate_bytecode_source(
        "(defeffect ask)\n(handle (+ (perform ask 3) 10) ((ask (arg k) (resume k (* arg 2)))))"
    )

    assert result == 16


# ---------------------------------------------------------------------------
# Phase H4: MIR verifier enhancement tests
# ---------------------------------------------------------------------------


def test_verify_mir_detects_unreachable_block():
    """An unreachable block (no path from entry) should produce a warning."""
    mir = MIRProgram(
        (
            MIRFunction(
                Symbol("test_unreachable"),
                (),
                2,
                (
                    # bb0: entry — jumps to itself (loop), no path to bb1
                    MIRBlock(0, (), MIRTerminator("JUMP", (0,))),
                    # bb1: unreachable — returns r0
                    MIRBlock(1, (), MIRTerminator("RETURN", (0,))),
                ),
                entry=0,
            ),
        )
    )

    diagnostics = verify_mir(mir)

    warnings = [d for d in diagnostics if d.severity == "warning"]
    assert any("block bb1 is unreachable from entry" in d.message for d in warnings), (
        f"Expected unreachable-block warning, got: {[d.message for d in warnings]}"
    )


def test_verify_mir_all_blocks_reachable_no_warning():
    """When all blocks are reachable, no unreachable warning should appear."""
    mir = MIRProgram(
        (
            MIRFunction(
                Symbol("test_reachable"),
                (),
                2,
                (
                    # bb0: entry — branch to bb0 or bb1
                    MIRBlock(
                        0,
                        (MIRInstruction("LOAD_CONST", (0, 0), None),),
                        MIRTerminator("BRANCH", (0, 0, 1)),
                    ),
                    # bb1: return r0
                    MIRBlock(1, (), MIRTerminator("RETURN", (0,))),
                ),
                entry=0,
            ),
        )
    )

    diagnostics = verify_mir(mir)

    warnings = [d for d in diagnostics if d.severity == "warning"]
    assert not any("unreachable" in d.message for d in warnings), (
        f"Unexpected unreachable warning: {[d.message for d in warnings]}"
    )


def test_verify_mir_detects_undefined_register():
    """Using a register before it is defined in a block should produce a warning."""
    mir = MIRProgram(
        (
            MIRFunction(
                Symbol("test_undef_reg"),
                (),
                3,
                (
                    MIRBlock(
                        0,
                        (
                            # r1 = LOAD_CONST 0  (defines r1)
                            MIRInstruction("LOAD_CONST", (1, 0), None),
                            # MOVE r0, r2  — r2 is never defined in this block
                            MIRInstruction("MOVE", (0, 2), None),
                        ),
                        MIRTerminator("RETURN", (0,)),
                    ),
                ),
                entry=0,
            ),
        )
    )

    diagnostics = verify_mir(mir)

    warnings = [d for d in diagnostics if d.severity == "warning"]
    assert any("uses register r2 before definition" in d.message for d in warnings), (
        f"Expected undef-register warning, got: {[d.message for d in warnings]}"
    )


def test_verify_mir_param_registers_considered_defined():
    """Parameter registers (r0, r1, ...) should be treated as pre-defined."""
    mir = MIRProgram(
        (
            MIRFunction(
                Symbol("test_params"),
                (Symbol("x"), Symbol("y")),
                2,
                (
                    MIRBlock(
                        0,
                        (
                            # MOVE r0, r1 — both are params, should be fine
                            MIRInstruction("MOVE", (0, 1), None),
                        ),
                        MIRTerminator("RETURN", (0,)),
                    ),
                ),
                entry=0,
            ),
        )
    )

    diagnostics = verify_mir(mir)

    warnings = [d for d in diagnostics if d.severity == "warning"]
    assert not any("before definition" in d.message for d in warnings), (
        f"Unexpected undef warning for param registers: {[d.message for d in warnings]}"
    )


def test_verify_mir_tail_call_structure_valid():
    """TAIL_CALL as terminator with 2 operands (register, tuple) should be accepted."""
    mir = MIRProgram(
        (
            MIRFunction(
                Symbol("test_tc"),
                (Symbol("x"),),
                2,
                (
                    MIRBlock(
                        0,
                        (MIRInstruction("LOAD_CONST", (1, 0), None),),
                        MIRTerminator("TAIL_CALL", (0, (1,))),
                    ),
                ),
                entry=0,
            ),
        )
    )

    diagnostics = verify_mir(mir)

    errors = [d for d in diagnostics if d.severity == "error"]
    assert not any("TAIL_CALL" in d.message for d in errors), (
        f"Unexpected TAIL_CALL errors: {[d.message for d in errors]}"
    )


def test_verify_mir_detects_undefined_register_in_terminator():
    """A terminator that uses an undefined register should also produce a warning."""
    mir = MIRProgram(
        (
            MIRFunction(
                Symbol("test_term_undef"),
                (),
                3,
                (
                    MIRBlock(
                        0,
                        (
                            # Only define r0
                            MIRInstruction("LOAD_CONST", (0, 0), None),
                        ),
                        # RETURN r2 — r2 never defined
                        MIRTerminator("RETURN", (2,)),
                    ),
                ),
                entry=0,
            ),
        )
    )

    diagnostics = verify_mir(mir)

    warnings = [d for d in diagnostics if d.severity == "warning"]
    assert any("uses register r2 before definition" in d.message for d in warnings), (
        f"Expected undef-register warning in terminator, got: {[d.message for d in warnings]}"
    )


def test_verify_mir_def_use_does_not_flag_append_result_as_definition():
    """APPEND_RESULT uses a register but does NOT define one; verify no false positives."""
    mir = MIRProgram(
        (
            MIRFunction(
                Symbol("test_append"),
                (),
                2,
                (
                    MIRBlock(
                        0,
                        (
                            MIRInstruction("LOAD_CONST", (0, 42), None),
                            MIRInstruction("APPEND_RESULT", (0,), None),
                        ),
                        MIRTerminator("RETURN", (None,)),
                    ),
                ),
                entry=0,
            ),
        )
    )

    diagnostics = verify_mir(mir)

    warnings = [d for d in diagnostics if d.severity == "warning"]
    assert not any("before definition" in d.message for d in warnings), (
        f"Unexpected false positive from APPEND_RESULT: {[d.message for d in warnings]}"
    )
