# coding: utf-8
"""optimize.cse pass.

Common Subexpression Elimination: detects instructions with identical
opcode and operands that compute the same value, and replaces later
uses with the result of the first computation.

Only applies to pure (side-effect-free) instructions.
"""

from __future__ import annotations

from typing import cast

from qy.ir.mir import MIRBlock
from qy.ir.mir import MIRFunction
from qy.ir.mir import MIRInstruction
from qy.ir.mir import MIRProgram
from qy.passes.pass_base import Pass
from qy.passes.pass_base import PassContext
from qy.passes.pass_base import PassResult

__all__ = ["CSEPass"]

_CSE_SAFE_OPCODES: frozenset[str] = frozenset(
    {
        "LOAD_CONST",
        "LOAD_HOST",
        "LOAD_ENV",
        "MAKE_FUNCTION",
        "MAKE_MACRO",
    }
)


class CSEPass(Pass):
    def __init__(self):
        super().__init__("optimize.cse")

    def run(self, context: PassContext) -> PassResult:
        program = cast(MIRProgram, context.input_artifact)
        new_functions = tuple(_eliminate_cse(f) for f in program.functions)
        return PassResult(
            success=True,
            artifact=MIRProgram(
                new_functions, program.constants, program.main, program.diagnostics
            ),
        )


def _eliminate_cse(function: MIRFunction) -> MIRFunction:
    changed = True
    blocks = list(function.blocks)

    while changed:
        changed = False
        # Map from (opcode, canonicalized_operands) -> dest_reg
        expr_map: dict[tuple[str, tuple[object, ...]], int] = {}
        # Track which registers have been redefined (invalidating the map)
        defs: set[int] = set()

        new_blocks: list[MIRBlock] = []
        for block in blocks:
            new_instructions: list[MIRInstruction] = []

            for inst in block.instructions:
                dest = _def(inst)
                if dest is not None:
                    defs.add(dest)
                    # Remove all expressions that produce this register
                    to_remove = [k for k, v in expr_map.items() if v == dest]
                    for k in to_remove:
                        del expr_map[k]

                if inst.opcode in _CSE_SAFE_OPCODES and dest is not None:
                    key = _canonicalize(inst)
                    existing = expr_map.get(key)
                    if existing is not None and existing not in defs:
                        # Replace with MOVE from the existing result
                        new_instructions.append(MIRInstruction("MOVE", (dest, existing), inst.span))
                        changed = True
                        continue
                    else:
                        expr_map[key] = dest

                new_instructions.append(inst)

            new_blocks.append(MIRBlock(block.id, tuple(new_instructions), block.terminator))
        blocks = new_blocks

    return MIRFunction(
        function.name,
        function.params,
        function.register_count,
        tuple(blocks),
        function.entry,
    )


def _canonicalize(inst: MIRInstruction) -> tuple[str, tuple[object, ...]]:
    """Create a canonical key for expression matching."""
    return (inst.opcode, inst.operands)


def _def(inst: MIRInstruction) -> int | None:
    if not inst.operands:
        return None
    dest = inst.operands[0]
    if not isinstance(dest, int):
        return None
    match inst.opcode:
        case "LOAD_CONST" | "LOAD_HOST" | "LOAD_ENV" | "MOVE":
            return dest
        case "MAKE_FUNCTION" | "MAKE_MACRO":
            return dest
        case _:
            return None
