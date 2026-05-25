# coding: utf-8
"""control.tailcall pass。.

Identifies missed tail call opportunities in MIR:
- CALL dest followed by RETURN dest → convert to TAIL_CALL
"""

from __future__ import annotations

from qy.ir.mir import MIRBlock
from qy.ir.mir import MIRFunction
from qy.ir.mir import MIRProgram
from qy.ir.mir import MIRTerminator
from qy.passes.pass_base import Pass
from qy.passes.pass_base import PassContext
from qy.passes.pass_base import PassResult

__all__ = ["TailCallPass"]


class TailCallPass(Pass):
    def __init__(self):
        super().__init__("control.tailcall")

    def run(self, context: PassContext) -> PassResult:
        from typing import cast

        program = cast(MIRProgram, context.input_artifact)
        new_functions = tuple(_optimize_function(f) for f in program.functions)
        return PassResult(
            success=True,
            artifact=MIRProgram(
                new_functions, program.constants, program.main, program.diagnostics
            ),
        )


def _optimize_function(function: MIRFunction) -> MIRFunction:
    new_blocks: list[MIRBlock] = []
    changed = False

    for block in function.blocks:
        if (
            block.terminator.opcode == "RETURN"
            and block.instructions
            and block.instructions[-1].opcode == "CALL"
        ):
            call = block.instructions[-1]
            from typing import cast

            dest_reg = cast(int, call.operands[0])
            return_reg = cast(int, block.terminator.operands[0])

            if dest_reg == return_reg:
                _, fn_reg, arg_regs = call.operands
                new_terminator = MIRTerminator(
                    "TAIL_CALL", (fn_reg, arg_regs), block.terminator.span
                )
                new_blocks.append(MIRBlock(block.id, block.instructions[:-1], new_terminator))
                changed = True
                continue

        new_blocks.append(block)

    if not changed:
        return function

    return MIRFunction(
        function.name,
        function.params,
        function.register_count,
        tuple(new_blocks),
        function.entry,
    )
