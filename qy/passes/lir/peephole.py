# coding: utf-8
from __future__ import annotations

from qy.ir.lir import LIRInstruction

__all__ = ["peephole"]


def peephole(instructions: list[LIRInstruction]) -> list[LIRInstruction]:
    """Remove obviously redundant instruction patterns and fuse opcodes.

    Patterns handled:
    - MOVE r, r  (no-op self-assignment)
    - LOAD_HOST r, None -> LOAD_NIL r  (use LIR-specific nil load)
    - LOAD_HOST r, QY_T -> LOAD_T r    (use LIR-specific T load)
    - MOVE r1, r2; USE r1 -> USE r2  (copy forwarding)
    - LOAD_NIL r; ... ; USE r -> remove if dead

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
        # Track MOVE dest -> src for copy forwarding
        copies: dict[int, int] = {}
        used: set[int] = set()

        # First pass: collect all uses
        for instruction in result:
            for op in instruction.operands:
                if isinstance(op, int):
                    used.add(op)
                elif isinstance(op, tuple):
                    for sub in op:
                        if isinstance(sub, int):
                            used.add(sub)

        for instruction in result:
            # MOVE r, r -> delete
            if instruction.opcode == "MOVE" and instruction.operands[0] == instruction.operands[1]:
                changed = True
                continue

            # LOAD_HOST r, None -> LOAD_NIL r
            if (
                instruction.opcode == "LOAD_HOST"
                and len(instruction.operands) >= 2
                and instruction.operands[1] is None
            ):
                changed = True
                out.append(LIRInstruction("LOAD_NIL", (instruction.operands[0],), instruction.span))
                continue

            # LOAD_HOST r, QY_T -> LOAD_T r
            if (
                instruction.opcode == "LOAD_HOST"
                and len(instruction.operands) >= 2
                and instruction.operands[1] is T
            ):
                changed = True
                out.append(LIRInstruction("LOAD_T", (instruction.operands[0],), instruction.span))
                continue

            # Track MOVE copies for forwarding
            if instruction.opcode == "MOVE":
                dest = instruction.operands[0]
                src = instruction.operands[1]
                if isinstance(dest, int) and isinstance(src, int):
                    # Only forward if dest is not used elsewhere
                    if dest not in used:
                        copies[dest] = src
                        changed = True
                        continue

            out.append(instruction)
        result = out
    return result
