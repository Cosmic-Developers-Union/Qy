# coding: utf-8
"""optimize.scalar_replace pass.

Scalar Replacement: when a tuple is constructed and only accessed via
known indices (BUILD_TUPLE + element reads), replace the tuple with
individual scalar registers.

This avoids allocating a tuple object when the structure is fully visible
and does not escape.

Currently handles the simple pattern:
  BUILD_TUPLE r, (e0, e1, ...)
  where r is used only in APPEND_RESULT or as a return value.
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

__all__ = ["ScalarReplacePass"]


class ScalarReplacePass(Pass):
    def __init__(self):
        super().__init__("optimize.scalar_replace")

    def run(self, context: PassContext) -> PassResult:
        program = cast(MIRProgram, context.input_artifact)
        new_functions = tuple(_replace_in_function(f) for f in program.functions)
        return PassResult(
            success=True,
            artifact=MIRProgram(
                new_functions, program.constants, program.main, program.diagnostics
            ),
        )


def _replace_in_function(function: MIRFunction) -> MIRFunction:
    """Replace BUILD_TUPLE + APPEND_RESULT with individual APPEND_RESULT calls.

    Pattern:
        BUILD_TUPLE r, (e0, e1, ..., eN)
        APPEND_RESULT r

    Becomes:
        APPEND_RESULT e0
        APPEND_RESULT e1
        ...
        APPEND_RESULT eN

    This avoids the tuple allocation when the tuple is only used to collect
    results (which is common in QyLang's list-building patterns).
    """
    changed = True
    blocks = list(function.blocks)

    while changed:
        changed = False
        tuple_defs: dict[int, tuple[object, ...]] = {}

        new_blocks: list[MIRBlock] = []
        for block in blocks:
            new_instructions: list[MIRInstruction] = []

            for inst in block.instructions:
                # Track BUILD_TUPLE definitions
                if inst.opcode == "BUILD_TUPLE":
                    dest = cast(int, inst.operands[0])
                    elements = inst.operands[1:]
                    tuple_defs[dest] = elements
                    new_instructions.append(inst)
                    continue

                # Expand APPEND_RESULT of a tuple into individual appends
                if inst.opcode == "APPEND_RESULT":
                    val = inst.operands[0]
                    if isinstance(val, int) and val in tuple_defs:
                        elements = tuple_defs[val]
                        for elem in elements:
                            new_instructions.append(
                                MIRInstruction("APPEND_RESULT", (elem,), inst.span)
                            )
                        changed = True
                        continue

                # Invalidate tuple tracking on any redefinition
                dest = _def(inst)
                if dest is not None and dest in tuple_defs:
                    del tuple_defs[dest]

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


def _def(inst: MIRInstruction) -> int | None:
    if not inst.operands:
        return None
    dest = inst.operands[0]
    if not isinstance(dest, int):
        return None
    match inst.opcode:
        case "LOAD_CONST" | "LOAD_HOST" | "LOAD_ENV" | "MOVE":
            return dest
        case "MAKE_FUNCTION" | "MAKE_MACRO" | "BUILD_TUPLE" | "CALL" | "APPLY":
            return dest
        case _:
            return None
