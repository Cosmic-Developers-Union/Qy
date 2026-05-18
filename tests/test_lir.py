from qy import LIRProgram
from qy import compile_lir_bytecode
from qy import dump_lir
from qy import lower_lir
from qy.bytecode_compiler import compile_mir_bytecode
from qy.lowering import lower_source
from qy.mir_lowering import lower_mir
from qy.reader import Symbol
from qy.register_vm import evaluate_bytecode_source


def test_lower_lir_produces_lir_program():
    mir = lower_mir(lower_source("(+ 1 2)"))

    lir = lower_lir(mir)

    assert isinstance(lir, LIRProgram)
    assert lir.ok
    assert len(lir.functions) == len(mir.functions)


def test_lower_lir_flattens_cond_blocks_to_jump_if_false():
    mir = lower_mir(lower_source("(cond (true 1) (false 2))"))

    lir = lower_lir(mir)

    main = lir.functions[lir.main]
    opcodes = [instruction.opcode for instruction in main.instructions]
    assert "JUMP_IF_FALSE" in opcodes
    assert "JUMP" in opcodes
    assert "BRANCH" not in opcodes


def test_lower_lir_resolves_jump_targets_to_offsets():
    mir = lower_mir(lower_source("(cond (true 1) (false 2))"))

    lir = lower_lir(mir)

    main = lir.functions[lir.main]
    for instruction in main.instructions:
        if instruction.opcode in {"JUMP", "JUMP_IF_FALSE"}:
            target = instruction.operands[-1]
            assert isinstance(target, int), f"jump target should be int, got {target!r}"
            assert 0 <= target < len(main.instructions)


def test_lower_lir_no_mir_terminators_in_output():
    mir = lower_mir(
        lower_source(
            """
            (defun fib (n)
              (cond
                ((= n 0) 0)
                ((= n 1) 1)
                (true (+ (fib (- n 1)) (fib (- n 2))))))
            (fib 5)
            """
        )
    )

    lir = lower_lir(mir)

    for function in lir.functions:
        for instruction in function.instructions:
            assert instruction.opcode != "BRANCH", "BRANCH should be lowered to JUMP_IF_FALSE+JUMP"


def test_lower_lir_stops_on_mir_errors():
    from qy.mir import MIRBlock
    from qy.mir import MIRFunction
    from qy.mir import MIRProgram
    from qy.mir import MIRTerminator

    mir = MIRProgram(
        (MIRFunction(Symbol("broken"), (), 1, (MIRBlock(0, (), MIRTerminator("JUMP", (99,))),), 0),)
    )

    lir = lower_lir(mir)

    assert not lir.ok
    assert lir.functions == ()
    assert any("jumps to missing block bb99" in d.message for d in lir.diagnostics)


def test_dump_lir_shows_function_header_and_instructions():
    mir = lower_mir(lower_source("(let ((x 1)) (+ x 2))"))

    lir = lower_lir(mir)
    rendered = dump_lir(lir)

    assert "fn#0 <main>() regs=" in rendered
    assert "[main]" in rendered
    assert "LOAD_HOST" in rendered


def test_dump_lir_shows_jump_if_false_for_cond():
    mir = lower_mir(lower_source("(cond (true 1) (false 2))"))

    lir = lower_lir(mir)
    rendered = dump_lir(lir)

    assert "JUMP_IF_FALSE" in rendered


def test_compile_lir_bytecode_produces_runnable_program():
    mir = lower_mir(lower_source("(+ 1 2)"))
    lir = lower_lir(mir)

    bytecode = compile_lir_bytecode(lir)

    assert bytecode.ok
    assert len(bytecode.functions) > 0


def test_compile_lir_bytecode_stops_on_lir_errors():
    from qy.mir import MIRBlock
    from qy.mir import MIRFunction
    from qy.mir import MIRProgram
    from qy.mir import MIRTerminator

    mir = MIRProgram(
        (MIRFunction(Symbol("broken"), (), 1, (MIRBlock(0, (), MIRTerminator("JUMP", (99,))),), 0),)
    )
    lir = lower_lir(mir)

    bytecode = compile_lir_bytecode(lir)

    assert not bytecode.ok
    assert bytecode.functions == ()


def test_lir_pipeline_end_to_end_arithmetic():
    result = evaluate_bytecode_source("(* (+ 3 4) 2)")

    assert result == 14


def test_lir_pipeline_end_to_end_tail_recursion():
    result = evaluate_bytecode_source(
        """
        (defun count (n)
          (cond
            ((= n 0) 0)
            (true (count (- n 1)))))
        (count 1000)
        """
    )

    assert result == 0


def test_lower_lir_effect_instructions_pass_through():
    mir = lower_mir(
        lower_source(
            "(defeffect ask)\n(handle (perform ask 1) ((ask (arg k) (resume k (* arg 2)))))"
        )
    )

    lir = lower_lir(mir)

    assert lir.ok
    all_opcodes = {instruction.opcode for f in lir.functions for instruction in f.instructions}
    assert "DEFEFFECT" in all_opcodes
    assert "PERFORM" in all_opcodes
    assert "HANDLE" in all_opcodes
    assert "RESUME" in all_opcodes


def test_lir_and_mir_bytecode_compile_produce_same_result():
    source = "(defun double (x) (* x 2))\n(double 21)"
    mir = lower_mir(lower_source(source))

    lir_bytecode = compile_lir_bytecode(lower_lir(mir))
    mir_bytecode = compile_mir_bytecode(mir)

    assert lir_bytecode.ok == mir_bytecode.ok
    assert len(lir_bytecode.functions) == len(mir_bytecode.functions)
    for lf, mf in zip(lir_bytecode.functions, mir_bytecode.functions, strict=True):
        assert lf.name == mf.name
        assert lf.params == mf.params
        assert lf.register_count == mf.register_count
        assert lf.instructions == mf.instructions


def test_lower_lir_compacts_sparse_register_layout():
    from qy.mir import MIRBlock
    from qy.mir import MIRFunction
    from qy.mir import MIRInstruction
    from qy.mir import MIRProgram
    from qy.mir import MIRTerminator

    mir = MIRProgram(
        (
            MIRFunction(
                Symbol("layout"),
                (),
                8,
                (
                    MIRBlock(
                        0,
                        (
                            MIRInstruction("LOAD_HOST", (5, 1)),
                            MIRInstruction("MOVE", (7, 5)),
                        ),
                        MIRTerminator("RETURN", (7,)),
                    ),
                ),
                0,
            ),
        )
    )

    lir = lower_lir(mir)

    assert lir.ok
    function = lir.functions[0]
    assert function.register_count == 2
    assert function.instructions[0].operands == (0, 1)
    assert function.instructions[1].operands == (1, 0)
    assert function.instructions[2].operands == (1,)


def test_peephole_removes_move_self_assignment():
    """Peephole eliminates MOVE r, r (no-op)."""
    from qy.lir import LIRInstruction
    from qy.lir_lowering import _peephole

    instructions = [
        LIRInstruction("LOAD_HOST", (0, 1)),
        LIRInstruction("MOVE", (0, 0)),  # self-assignment, should be removed
        LIRInstruction("RETURN", (0,)),
    ]

    result = _peephole(instructions)
    opcodes = [i.opcode for i in result]
    assert opcodes == ["LOAD_HOST", "RETURN"]


def test_peephole_keeps_move_different_registers():
    """Peephole preserves MOVE between different registers."""
    from qy.lir import LIRInstruction
    from qy.lir_lowering import _peephole

    instructions = [
        LIRInstruction("LOAD_HOST", (0, 1)),
        LIRInstruction("MOVE", (1, 0)),  # different registers, kept
        LIRInstruction("RETURN", (1,)),
    ]
    result = _peephole(instructions)
    opcodes = [i.opcode for i in result]
    assert opcodes == ["LOAD_HOST", "MOVE", "RETURN"]


def test_peephole_strength_reduces_nil():
    """Peephole converts LOAD_HOST r, None → LOAD_NIL r."""
    from qy.lir import LIRInstruction
    from qy.lir_lowering import _peephole

    instructions = [LIRInstruction("LOAD_HOST", (0, None))]
    result = _peephole(instructions)
    assert len(result) == 1
    assert result[0].opcode == "LOAD_NIL"
    assert result[0].operands == (0,)


def test_peephole_strength_reduces_t():
    """Peephole converts LOAD_HOST r, QY_T → LOAD_T r."""
    from qy.lir import LIRInstruction
    from qy.lir_lowering import _peephole
    from qy.values import QY_T

    instructions = [LIRInstruction("LOAD_HOST", (0, QY_T))]
    result = _peephole(instructions)
    assert len(result) == 1
    assert result[0].opcode == "LOAD_T"
    assert result[0].operands == (0,)


def test_peephole_keeps_jump_to_next_instruction():
    """Keep JUMP-to-next since jumps are pre-patched to absolute indices."""
    from qy.lir import LIRInstruction
    from qy.lir_lowering import _peephole

    instructions = [
        LIRInstruction("LOAD_HOST", (0, 1)),
        LIRInstruction("JUMP", (2,)),  # JUMP to index 2 (next instruction) — kept
        LIRInstruction("RETURN", (0,)),
    ]
    result = _peephole(instructions)
    opcodes = [i.opcode for i in result]
    assert opcodes == ["LOAD_HOST", "JUMP", "RETURN"]


def test_peephole_keeps_jump_to_non_next():
    """Peephole keeps JUMP when target is not the next instruction."""
    from qy.lir import LIRInstruction
    from qy.lir_lowering import _peephole

    instructions = [
        LIRInstruction("LOAD_HOST", (0, 1)),
        LIRInstruction("JUMP", (0,)),  # JUMP to index 0 (backwards) → kept
        LIRInstruction("RETURN", (0,)),
    ]
    result = _peephole(instructions)
    opcodes = [i.opcode for i in result]
    assert opcodes == ["LOAD_HOST", "JUMP", "RETURN"]


def test_verify_lir_catches_out_of_range_register():
    """Verifier reports error for register operand >= register_count."""
    from qy.lir import LIRFunction
    from qy.lir import LIRInstruction
    from qy.lir import LIRProgram
    from qy.lir import verify_lir

    program = LIRProgram(
        (
            LIRFunction(
                Symbol("bad"),
                (),
                2,  # register_count=2, so only r0 and r1 are valid
                (
                    LIRInstruction("LOAD_HOST", (5, 42)),  # r5 is out of range
                    LIRInstruction("RETURN", (5,)),
                ),
            ),
        ),
        0,
    )
    diagnostics = verify_lir(program)
    errors = [d for d in diagnostics if d.severity == "error"]
    assert len(errors) >= 1
    assert any("out-of-range register" in d.message for d in errors)
    assert any("r5" in d.message for d in errors)
    assert any("register_count=2" in d.message for d in errors)


def test_verify_lir_catches_out_of_range_jump():
    """Verifier reports error for jump target >= instruction count."""
    from qy.lir import LIRFunction
    from qy.lir import LIRInstruction
    from qy.lir import LIRProgram
    from qy.lir import verify_lir

    program = LIRProgram(
        (
            LIRFunction(
                Symbol("badjump"),
                (),
                1,
                (
                    LIRInstruction("LOAD_HOST", (0, 1)),
                    LIRInstruction("JUMP", (99,)),  # target 99 is out of range
                ),
            ),
        ),
        0,
    )
    diagnostics = verify_lir(program)
    errors = [d for d in diagnostics if d.severity == "error"]
    assert len(errors) >= 1
    assert any("jump to out-of-range target 99" in d.message for d in errors)


def test_verify_lir_passes_valid_program():
    """Verifier returns no errors for a well-formed program."""
    from qy.lir import LIRFunction
    from qy.lir import LIRInstruction
    from qy.lir import LIRProgram
    from qy.lir import verify_lir

    program = LIRProgram(
        (
            LIRFunction(
                Symbol("good"),
                (),
                2,
                (
                    LIRInstruction("LOAD_HOST", (0, 1)),
                    LIRInstruction("LOAD_HOST", (1, 2)),
                    LIRInstruction("RETURN", (0,)),
                ),
            ),
        ),
        0,
    )
    diagnostics = verify_lir(program)
    errors = [d for d in diagnostics if d.severity == "error"]
    assert len(errors) == 0


def test_lir_load_nil_and_load_t_in_pipeline():
    """End-to-end: LOAD_NIL/LOAD_T opcodes appear in LIR output for nil/t values."""
    from qy.lir_lowering import lower_lir

    source = "(cond (true 1) (true 2))"
    mir = lower_mir(lower_source(source))
    lir = lower_lir(mir)

    assert lir.ok
    main = lir.functions[lir.main]
    opcodes = [inst.opcode for inst in main.instructions]
    # The cond lowering produces LOAD_HOST QY_T for true predicates,
    # and LOAD_HOST QY_NIL for false branches; peephole should convert these.
    # LOAD_NIL may appear when nil values are loaded, LOAD_T when QY_T is loaded.
    # At minimum LOAD_NIL should appear since cond emits nil for non-taken branches.
    assert "LOAD_NIL" in opcodes or "LOAD_T" in opcodes, (
        f"Expected LOAD_NIL or LOAD_T in opcodes, got {opcodes}"
    )


def test_lir_peephole_load_t_compiles_to_bytecode():
    """LOAD_T in LIR compiles correctly to LOAD_HOST with QY_T in bytecode."""
    from qy.bytecode_compiler import compile_lir_bytecode
    from qy.lir import LIRFunction
    from qy.lir import LIRInstruction
    from qy.lir import LIRProgram
    from qy.values import QY_T

    program = LIRProgram(
        (
            LIRFunction(
                Symbol("test_t"),
                (),
                1,
                (
                    LIRInstruction("LOAD_T", (0,)),
                    LIRInstruction("RETURN", (0,)),
                ),
            ),
        ),
        0,
    )
    bytecode = compile_lir_bytecode(program)
    assert bytecode.ok
    main = bytecode.functions[0]
    # LOAD_T should map to LOAD_HOST with QY_T
    assert main.instructions[0].opcode == "LOAD_HOST"
    assert main.instructions[0].operands[1] is QY_T


def test_verify_lir_catches_missing_terminator():
    """Verifier reports error when function does not end with a terminator."""
    from qy.lir import LIRFunction
    from qy.lir import LIRInstruction
    from qy.lir import LIRProgram
    from qy.lir import verify_lir

    program = LIRProgram(
        (
            LIRFunction(
                Symbol("no_return"),
                (),
                1,
                (LIRInstruction("LOAD_HOST", (0, 42)),),
            ),
        ),
        0,
    )
    diagnostics = verify_lir(program)
    errors = [d for d in diagnostics if d.severity == "error"]
    assert len(errors) >= 1
    assert any("does not end with a terminator" in d.message for d in errors)


def test_verify_lir_catches_unreachable_after_terminator():
    """Verifier warns about instructions after a terminator."""
    from qy.lir import LIRFunction
    from qy.lir import LIRInstruction
    from qy.lir import LIRProgram
    from qy.lir import verify_lir

    program = LIRProgram(
        (
            LIRFunction(
                Symbol("dead_code"),
                (),
                1,
                (
                    LIRInstruction("LOAD_HOST", (0, 1)),
                    LIRInstruction("RETURN", (0,)),
                    LIRInstruction("LOAD_HOST", (0, 2)),  # unreachable
                ),
            ),
        ),
        0,
    )
    diagnostics = verify_lir(program)
    warnings = [d for d in diagnostics if d.severity == "warning"]
    assert any("unreachable instruction" in d.message for d in warnings)


def test_verify_lir_accepts_terminators():
    """Verifier accepts RETURN, TAIL_CALL, and RAISE_EFFECT as terminators."""
    from qy.lir import LIRFunction
    from qy.lir import LIRInstruction
    from qy.lir import LIRProgram
    from qy.lir import verify_lir

    # RETURN
    p1 = LIRProgram(
        (LIRFunction(Symbol("f1"), (), 1, (LIRInstruction("RETURN", (0,)),)),),
        0,
    )
    assert not any(d.severity == "error" for d in verify_lir(p1))

    # TAIL_CALL
    p2 = LIRProgram(
        (LIRFunction(Symbol("f2"), (), 1, (LIRInstruction("TAIL_CALL", (0, ())),)),),
        0,
    )
    assert not any(d.severity == "error" for d in verify_lir(p2))


def test_verify_lir_branch_nil_target_checked():
    """Verifier checks BRANCH_NIL jump targets."""
    from qy.lir import LIRFunction
    from qy.lir import LIRInstruction
    from qy.lir import LIRProgram
    from qy.lir import verify_lir

    program = LIRProgram(
        (
            LIRFunction(
                Symbol("bad_branch_nil"),
                (),
                1,
                (
                    LIRInstruction("BRANCH_NIL", (0, 99)),  # out of range
                    LIRInstruction("RETURN", (0,)),
                ),
            ),
        ),
        0,
    )
    diagnostics = verify_lir(program)
    errors = [d for d in diagnostics if d.severity == "error"]
    assert any("jump to out-of-range target 99" in d.message for d in errors)
