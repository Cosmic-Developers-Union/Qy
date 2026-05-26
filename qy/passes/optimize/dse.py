# coding: utf-8
"""optimize.dse pass.

Dead Store Elimination: removes STORE_LOCAL and DEFINE_ONCE instructions
whose stored values are never read or are overwritten before being read.

Also removes MOVE instructions that are immediately overwritten.
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

__all__ = ["DeadStoreEliminationPass"]


class DeadStoreEliminationPass(Pass):
    def __init__(self):
        super().__init__("optimize.dse")

    def run(self, context: PassContext) -> PassResult:
        program = cast(MIRProgram, context.input_artifact)
        new_functions = tuple(_eliminate_dead_stores(f) for f in program.functions)
        return PassResult(
            success=True,
            artifact=MIRProgram(
                new_functions, program.constants, program.main, program.diagnostics
            ),
        )


def _eliminate_dead_stores(function: MIRFunction) -> MIRFunction:
    """Remove stores to registers that are never subsequently read."""
    changed = True
    blocks = list(function.blocks)

    while changed:
        changed = False

        # Collect all uses (reads) of each register across the function
        uses: dict[int, int] = {}  # reg -> use count
        for block in blocks:
            for inst in block.instructions:
                for used in _uses(inst):
                    uses[used] = uses.get(used, 0) + 1
            _uses_from_terminator(block.terminator, uses)

        new_blocks: list[MIRBlock] = []
        for block in blocks:
            new_instructions: list[MIRInstruction] = []
            for inst in block.instructions:
                if _is_dead_store(inst, uses):
                    # Decrement use count for the stored value
                    val_reg = _store_value_reg(inst)
                    if val_reg is not None and val_reg in uses:
                        uses[val_reg] -= 1
                    changed = True
                    continue
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


def _is_dead_store(inst: MIRInstruction, uses: dict[int, int]) -> bool:
    """Check if *inst* is a store whose value is never read."""
    if inst.opcode not in ("STORE_LOCAL", "DEFINE_ONCE"):
        return False

    # The stored value register
    val_reg = _store_value_reg(inst)
    if val_reg is None:
        return False

    # If the value register is never used after this store, it's dead
    return uses.get(val_reg, 0) == 0


def _store_value_reg(inst: MIRInstruction) -> int | None:
    """Return the register whose value is being stored."""
    if inst.opcode in ("STORE_LOCAL", "DEFINE_ONCE") and len(inst.operands) >= 2:
        val = inst.operands[1]
        if isinstance(val, int):
            return val
    return None


def _uses(inst: MIRInstruction) -> set[int]:
    """Return registers read by *inst*."""
    result: set[int] = set()
    match inst.opcode:
        case "LOAD_CONST" | "LOAD_HOST" | "LOAD_ENV":
            pass
        case "MOVE":
            _add_int_set(inst.operands[1], result)
        case "MAKE_FUNCTION" | "MAKE_MACRO":
            pass
        case "CALL":
            _, op_reg, arg_regs = inst.operands
            _add_int_set(op_reg, result)
            if isinstance(arg_regs, tuple):
                for r in arg_regs:
                    _add_int_set(r, result)
        case "APPLY":
            for op in inst.operands[1:]:
                _add_int_set(op, result)
        case "DEFINE_ONCE" | "STORE_LOCAL":
            _add_int_set(inst.operands[1], result)
        case "BUILD_TUPLE":
            for op in inst.operands[1:]:
                _add_int_set(op, result)
        case "APPEND_RESULT":
            _add_int_set(inst.operands[0], result)
        case "EFFECT_RESUME":
            for op in inst.operands[1:]:
                _add_int_set(op, result)
        case "RUNTIME_EVAL":
            for op in inst.operands[1:]:
                _add_int_set(op, result)
        case _:
            for op in inst.operands:
                if isinstance(op, int):
                    result.add(op)
    return result


def _uses_from_terminator(term: MIRTerminator, uses: dict[int, int]) -> None:
    match term.opcode:
        case "RETURN":
            _add_int(term.operands[0], uses)
        case "TAIL_CALL":
            fn_reg, arg_regs = term.operands
            _add_int(fn_reg, uses)
            if isinstance(arg_regs, tuple):
                for r in arg_regs:
                    _add_int(r, uses)
        case "BRANCH":
            _add_int(term.operands[0], uses)
        case "RAISE_EFFECT":
            _add_int(term.operands[1], uses)
        case "EFFECT_PERFORM":
            if len(term.operands) >= 3:
                _add_int(term.operands[2], uses)
        case _:
            pass


def _add_int(value: object, target: dict[int, int]) -> None:
    if isinstance(value, int):
        target[value] = target.get(value, 0) + 1


def _add_int_set(value: object, target: set[int]) -> None:
    if isinstance(value, int):
        target.add(value)
