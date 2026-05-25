# coding: utf-8
from __future__ import annotations

from qy.ir.lir import LIRInstruction

__all__ = ["peephole"]


def peephole(instructions: list[LIRInstruction]) -> list[LIRInstruction]:
    """Remove obviously redundant instruction patterns.

    Currently handles:
    - MOVE r, r  (no-op self-assignment)
    - LOAD_HOST r, None -> LOAD_NIL r  (use LIR-specific nil load)
    - LOAD_HOST r, QY_T -> LOAD_T r    (use LIR-specific T load)

    NOTE: JUMP-to-next elimination is NOT safe here because jumps have
    already been patched to absolute indices.  Removing a JUMP shifts all
    subsequent indices but does not update other jump targets.
    """
    from qy.sem.core import T

    result = list(instructions)
    changed = True
    while changed:
        changed = False
        out: list[LIRInstruction] = []
        for instruction in result:
            if instruction.opcode == "MOVE" and instruction.operands[0] == instruction.operands[1]:
                changed = True
                continue
            if (
                instruction.opcode == "LOAD_HOST"
                and len(instruction.operands) >= 2
                and instruction.operands[1] is None
            ):
                changed = True
                out.append(LIRInstruction("LOAD_NIL", (instruction.operands[0],), instruction.span))
                continue
            if (
                instruction.opcode == "LOAD_HOST"
                and len(instruction.operands) >= 2
                and instruction.operands[1] is T
            ):
                changed = True
                out.append(LIRInstruction("LOAD_T", (instruction.operands[0],), instruction.span))
                continue
            out.append(instruction)
        result = out
    return result
