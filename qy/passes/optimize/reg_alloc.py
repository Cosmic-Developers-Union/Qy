# coding: utf-8
"""optimize.reg_alloc pass.

Register allocation at the MIR level using liveness-based linear scan.

After all MIR transforms, this pass renumbers virtual registers to minimize
the total register count per function.  It uses liveness intervals to
determine which registers can share the same physical slot.
"""

from __future__ import annotations

from typing import cast

from qy.ir.mir import MIRBlock
from qy.ir.mir import MIRFunction
from qy.ir.mir import MIRInstruction
from qy.ir.mir import MIRProgram
from qy.ir.mir import MIRTerminator
from qy.passes.pass_base import Pass
from qy.passes.pass_base import PassContext
from qy.passes.pass_base import PassResult

__all__ = ["RegisterAllocationPass"]


class RegisterAllocationPass(Pass):
    def __init__(self):
        super().__init__("optimize.reg_alloc")

    def run(self, context: PassContext) -> PassResult:
        program = cast(MIRProgram, context.input_artifact)
        new_functions = tuple(_allocate_registers(f) for f in program.functions)
        return PassResult(
            success=True,
            artifact=MIRProgram(
                new_functions, program.constants, program.main, program.diagnostics
            ),
        )


def _allocate_registers(function: MIRFunction) -> MIRFunction:
    """Linear scan register allocation.

    Assigns physical register numbers to virtual registers based on
    liveness intervals.  Registers with non-overlapping live ranges
    can share the same physical register.
    """
    from qy.analysis.liveness import compute_liveness

    info = compute_liveness(function)
    intervals = info.intervals.intervals

    if not intervals:
        return function

    # Sort intervals by start position
    sorted_regs = sorted(intervals.keys(), key=lambda r: intervals[r][0])

    # Linear scan: assign physical registers
    # physical_reg -> end position of the last interval assigned to it
    physical_map: dict[int, int] = {}  # physical_reg -> last_end
    reg_to_physical: dict[int, int] = {}  # virtual_reg -> physical_reg
    next_physical = 0

    for vreg in sorted_regs:
        start, end = intervals[vreg]

        # Find a free physical register
        assigned = False
        for preg, last_end in physical_map.items():
            if last_end < start:
                reg_to_physical[vreg] = preg
                physical_map[preg] = end
                assigned = True
                break

        if not assigned:
            reg_to_physical[vreg] = next_physical
            physical_map[next_physical] = end
            next_physical += 1

    # Apply the register mapping
    new_blocks = tuple(_remap_block(block, reg_to_physical) for block in function.blocks)

    new_register_count = max(next_physical, len(function.params))

    return MIRFunction(
        function.name,
        function.params,
        new_register_count,
        new_blocks,
        function.entry,
    )


def _remap_block(block: MIRBlock, reg_map: dict[int, int]) -> MIRBlock:
    """Remap all register references in a block."""
    new_instructions = tuple(_remap_instruction(inst, reg_map) for inst in block.instructions)
    new_terminator = _remap_terminator(block.terminator, reg_map)
    return MIRBlock(block.id, new_instructions, new_terminator)


def _remap_instruction(inst: MIRInstruction, reg_map: dict[int, int]) -> MIRInstruction:
    """Remap register references in an instruction."""
    match inst.opcode:
        case "LOAD_CONST" | "LOAD_HOST" | "LOAD_ENV":
            dest = inst.operands[0]
            new_dest = reg_map.get(dest, dest) if isinstance(dest, int) else dest
            return MIRInstruction(inst.opcode, (new_dest, *inst.operands[1:]), inst.span)
        case "MOVE":
            dst, src = inst.operands
            new_dst = reg_map.get(dst, dst) if isinstance(dst, int) else dst
            new_src = reg_map.get(src, src) if isinstance(src, int) else src
            return MIRInstruction("MOVE", (new_dst, new_src), inst.span)
        case "MAKE_FUNCTION":
            dest = inst.operands[0]
            new_dest = reg_map.get(dest, dest) if isinstance(dest, int) else dest
            return MIRInstruction("MAKE_FUNCTION", (new_dest, inst.operands[1]), inst.span)
        case "MAKE_MACRO":
            dest = inst.operands[0]
            new_dest = reg_map.get(dest, dest) if isinstance(dest, int) else dest
            return MIRInstruction("MAKE_MACRO", (new_dest, *inst.operands[1:]), inst.span)
        case "CALL":
            dest, op_reg, arg_regs = inst.operands
            new_dest = reg_map.get(dest, dest) if isinstance(dest, int) else dest
            new_op = reg_map.get(op_reg, op_reg) if isinstance(op_reg, int) else op_reg
            new_args: tuple[object, ...] = ()
            if isinstance(arg_regs, tuple):
                new_args = tuple(reg_map.get(a, a) if isinstance(a, int) else a for a in arg_regs)
            return MIRInstruction("CALL", (new_dest, new_op, new_args), inst.span)
        case "APPLY":
            new_ops = tuple(reg_map.get(o, o) if isinstance(o, int) else o for o in inst.operands)
            return MIRInstruction("APPLY", new_ops, inst.span)
        case "DEFINE_ONCE":
            sym, val = inst.operands
            new_val = reg_map.get(val, val) if isinstance(val, int) else val
            return MIRInstruction("DEFINE_ONCE", (sym, new_val), inst.span)
        case "STORE_LOCAL":
            sym, val = inst.operands
            new_val = reg_map.get(val, val) if isinstance(val, int) else val
            return MIRInstruction("STORE_LOCAL", (sym, new_val), inst.span)
        case "BUILD_TUPLE":
            new_ops = tuple(reg_map.get(o, o) if isinstance(o, int) else o for o in inst.operands)
            return MIRInstruction("BUILD_TUPLE", new_ops, inst.span)
        case "APPEND_RESULT":
            val = inst.operands[0]
            new_val = reg_map.get(val, val) if isinstance(val, int) else val
            return MIRInstruction("APPEND_RESULT", (new_val,), inst.span)
        case "RUNTIME_EVAL":
            new_ops = tuple(reg_map.get(o, o) if isinstance(o, int) else o for o in inst.operands)
            return MIRInstruction("RUNTIME_EVAL", new_ops, inst.span)
        case "EFFECT_RESUME":
            new_ops = tuple(reg_map.get(o, o) if isinstance(o, int) else o for o in inst.operands)
            return MIRInstruction("EFFECT_RESUME", new_ops, inst.span)
        case _:
            return inst


def _remap_terminator(term: MIRTerminator, reg_map: dict[int, int]) -> MIRTerminator:
    """Remap register references in a terminator."""

    def _r(val: object) -> object:
        return reg_map.get(val, val) if isinstance(val, int) else val

    match term.opcode:
        case "RETURN":
            return MIRTerminator("RETURN", (_r(term.operands[0]),), term.span)
        case "TAIL_CALL":
            fn_reg, arg_regs = term.operands
            new_args = (
                tuple(_r(a) for a in cast(tuple, arg_regs))
                if isinstance(arg_regs, tuple)
                else arg_regs
            )
            return MIRTerminator("TAIL_CALL", (_r(fn_reg), new_args), term.span)
        case "BRANCH":
            cond, true_b, false_b = term.operands
            return MIRTerminator("BRANCH", (_r(cond), true_b, false_b), term.span)
        case "RAISE_EFFECT":
            return MIRTerminator(
                "RAISE_EFFECT",
                (term.operands[0], _r(term.operands[1]), term.operands[2]),
                term.span,
            )
        case "EFFECT_PERFORM":
            if len(term.operands) >= 3:
                new_ops = list(term.operands)
                new_ops[2] = _r(new_ops[2])
                return MIRTerminator(term.opcode, tuple(new_ops), term.span)
            return term
        case _:
            return term
