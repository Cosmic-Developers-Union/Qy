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
                ((eq n 0) 0)
                ((eq n 1) 1)
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
            ((eq n 0) 0)
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
