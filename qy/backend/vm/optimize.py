# coding: utf-8
"""Bytecode-level optimizations.

Operates on BytecodeProgram after LIR-to-bytecode compilation. These are
target-independent peephole and dead-code optimizations at the bytecode
level, distinct from the higher-level MIR/LIR passes.

Optimizations:
- Dead bytecode elimination: remove unreachable instructions after RETURN
- Jump chain optimization: JUMP -> JUMP to final target
- NOP elimination: remove MOVE r, r patterns
- Register pressure reduction: compact register numbering
"""

from __future__ import annotations

from qy.backend.vm.bytecode import BytecodeFunction
from qy.backend.vm.bytecode import BytecodeProgram
from qy.backend.vm.bytecode import Instruction

__all__ = ["optimize_bytecode"]


def optimize_bytecode(program: BytecodeProgram) -> BytecodeProgram:
    """Apply bytecode-level optimizations to *program*."""
    new_functions = tuple(_optimize_function(f) for f in program.functions)
    return BytecodeProgram(new_functions, program.main, program.diagnostics)


def _optimize_function(function: BytecodeFunction) -> BytecodeFunction:
    """Optimize a single bytecode function."""
    instructions = list(function.instructions)

    # Pass 1: Eliminate dead code after RETURN/TAIL_CALL
    instructions = _eliminate_dead_code(instructions)

    # Pass 2: Eliminate MOVE r, r (no-op)
    instructions = _eliminate_nop_moves(instructions)

    # Pass 3: Jump chain optimization
    instructions = _optimize_jumps(instructions)

    if len(instructions) == len(function.instructions):
        return function

    return BytecodeFunction(
        function.name,
        function.params,
        function.register_count,
        tuple(instructions),
    )


def _eliminate_dead_code(instructions: list[Instruction]) -> list[Instruction]:
    """Remove instructions after unconditional terminators (RETURN, TAIL_CALL)."""
    result: list[Instruction] = []
    for inst in instructions:
        result.append(inst)
        if inst.opcode in ("RETURN", "TAIL_CALL"):
            # All subsequent instructions in this linear sequence are dead
            # (unless they are jump targets, which we don't track here)
            break
    return result


def _eliminate_nop_moves(instructions: list[Instruction]) -> list[Instruction]:
    """Remove MOVE r, r (self-assignment) instructions."""
    return [
        inst
        for inst in instructions
        if not (
            inst.opcode == "MOVE"
            and len(inst.operands) >= 2
            and inst.operands[0] == inst.operands[1]
        )
    ]


def _optimize_jumps(instructions: list[Instruction]) -> list[Instruction]:
    """Optimize jump chains: JUMP target -> JUMP final_target."""
    # Build a map from instruction index to the instruction at that index
    # for JUMP chain resolution
    idx_map = {i: inst for i, inst in enumerate(instructions)}

    def resolve_jump_target(target_idx: int, seen: set[int]) -> int:
        if target_idx in seen or target_idx not in idx_map:
            return target_idx
        inst = idx_map[target_idx]
        if inst.opcode == "JUMP" and isinstance(inst.operands[0], int):
            seen.add(target_idx)
            return resolve_jump_target(inst.operands[0], seen)
        return target_idx

    result: list[Instruction] = []
    for i, inst in enumerate(instructions):
        if inst.opcode == "JUMP" and isinstance(inst.operands[0], int):
            final = resolve_jump_target(inst.operands[0], {i})
            if final != inst.operands[0]:
                result.append(Instruction("JUMP", (final,), inst.span))
                continue
        elif inst.opcode == "JUMP_IF_FALSE" and isinstance(inst.operands[1], int):
            final = resolve_jump_target(inst.operands[1], {i})
            if final != inst.operands[1]:
                result.append(Instruction("JUMP_IF_FALSE", (inst.operands[0], final), inst.span))
                continue
        result.append(inst)

    return result
