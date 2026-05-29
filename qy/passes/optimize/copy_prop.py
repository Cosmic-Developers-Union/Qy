# coding: utf-8
"""optimize.copy_prop pass.

Copy propagation: replaces uses of MOVE dest, src with direct uses of src
when there is no intervening redefinition of either register.

This eliminates redundant MOVE instructions and enables further optimization
by DCE and constant propagation.
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

__all__ = ["CopyPropagationPass"]


class CopyPropagationPass(Pass):
    def __init__(self):
        super().__init__("optimize.copy_prop")

    def run(self, context: PassContext) -> PassResult:
        program = cast(MIRProgram, context.input_artifact)
        new_functions = tuple(_propagate_in_function(f) for f in program.functions)
        return PassResult(
            success=True,
            artifact=MIRProgram(
                new_functions, program.constants, program.main, program.diagnostics
            ),
        )


def _propagate_in_function(function: MIRFunction) -> MIRFunction:
    changed = True
    blocks = list(function.blocks)

    while changed:
        changed = False

        # Build copy map: dest -> src for MOVE instructions
        copies: dict[int, int] = {}
        defs: set[int] = set()

        new_blocks: list[MIRBlock] = []
        for block in blocks:
            new_instructions: list[MIRInstruction] = []
            for inst in block.instructions:
                # Invalidate copies when dest is redefined
                dest = _def(inst)
                if dest is not None:
                    copies.pop(dest, None)
                    defs.add(dest)

                if inst.opcode == "MOVE":
                    src_val = inst.operands[1]
                    if isinstance(src_val, int) and src_val not in defs:
                        copies[cast(int, inst.operands[0])] = src_val

                new_inst = _substitute_instruction(inst, copies)
                if new_inst is not inst:
                    changed = True
                new_instructions.append(new_inst)

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


def _substitute_instruction(inst: MIRInstruction, copies: dict[int, int]) -> MIRInstruction:
    """Replace uses of copied registers with their source registers."""
    match inst.opcode:
        case "MOVE":
            src = inst.operands[1]
            if isinstance(src, int) and src in copies:
                new_src = copies[src]
                if new_src != src:
                    return MIRInstruction("MOVE", (inst.operands[0], new_src), inst.span)
            return inst
        case "CALL":
            dest, op_reg, arg_regs = inst.operands
            new_op = copies.get(op_reg, op_reg) if isinstance(op_reg, int) else op_reg
            new_args: tuple[object, ...] = ()
            if isinstance(arg_regs, tuple):
                new_args = tuple(copies.get(a, a) if isinstance(a, int) else a for a in arg_regs)
            if new_op != op_reg or new_args != arg_regs:
                return MIRInstruction("CALL", (dest, new_op, new_args), inst.span)
            return inst
        case "DEFINE_ONCE":
            val = inst.operands[1]
            if isinstance(val, int) and val in copies:
                new_val = copies[val]
                if new_val != val:
                    return MIRInstruction("DEFINE_ONCE", (inst.operands[0], new_val), inst.span)
            return inst
        case "STORE_LOCAL":
            val = inst.operands[1]
            if isinstance(val, int) and val in copies:
                new_val = copies[val]
                if new_val != val:
                    return MIRInstruction("STORE_LOCAL", (inst.operands[0], new_val), inst.span)
            return inst
        case "BUILD_TUPLE":
            new_ops = tuple(
                copies.get(op, op) if isinstance(op, int) else op for op in inst.operands
            )
            if new_ops != inst.operands:
                return MIRInstruction(inst.opcode, new_ops, inst.span)
            return inst
        case "APPEND_RESULT":
            val = inst.operands[0]
            if isinstance(val, int) and val in copies:
                new_val = copies[val]
                if new_val != val:
                    return MIRInstruction("APPEND_RESULT", (new_val,), inst.span)
            return inst
        case "EFFECT_RESUME":
            new_ops = tuple(
                copies.get(op, op) if isinstance(op, int) else op for op in inst.operands
            )
            if new_ops != inst.operands:
                return MIRInstruction(inst.opcode, new_ops, inst.span)
            return inst
        case _:
            return inst
