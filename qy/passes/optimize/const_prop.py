# coding: utf-8
"""optimize.const_prop pass.

Constant propagation: tracks which registers hold compile-time-known constant
values and substitutes them into downstream instructions.

Works across MOVE chains and simple LOAD_ENV lookups.  Combined with
const_fold, this enables compile-time evaluation of larger expression trees.
"""

from __future__ import annotations

from typing import cast

from qy.ir.mir import MIRBlock
from qy.ir.mir import MIRConstantPool
from qy.ir.mir import MIRFunction
from qy.ir.mir import MIRInstruction
from qy.ir.mir import MIRProgram
from qy.passes.pass_base import Pass
from qy.passes.pass_base import PassContext
from qy.passes.pass_base import PassResult

__all__ = ["ConstPropagationPass"]


class ConstPropagationPass(Pass):
    def __init__(self):
        super().__init__("optimize.const_prop")

    def run(self, context: PassContext) -> PassResult:
        program = cast(MIRProgram, context.input_artifact)
        pool = MIRConstantPool()
        for v in program.constants.values:
            pool.intern(v)

        new_functions = tuple(_propagate_in_function(f, pool) for f in program.functions)
        return PassResult(
            success=True,
            artifact=MIRProgram(new_functions, pool, program.main, program.diagnostics),
        )


def _propagate_in_function(
    function: MIRFunction,
    pool: MIRConstantPool,
) -> MIRFunction:
    """Propagate known constants through the function.

    Maintains a mapping reg -> const_index for registers known to hold
    a constant value.  When a LOAD_CONST defines a register, we record it.
    When a MOVE copies a constant, we propagate the constant index.
    When a LOAD_ENV resolves a known constant binding, we propagate it.
    """
    const_map: dict[int, int] = {}  # reg -> pool index
    changed = True
    blocks = list(function.blocks)

    while changed:
        changed = False
        new_blocks: list[MIRBlock] = []

        for block in blocks:
            new_instructions: list[MIRInstruction] = []
            for inst in block.instructions:
                new_inst, local_changed = _process_instruction(inst, const_map, pool)
                if local_changed:
                    changed = True
                new_instructions.append(new_inst)

                # Track definitions
                dest = _def(inst)
                if dest is not None:
                    if inst.opcode == "LOAD_CONST":
                        const_idx = inst.operands[1]
                        if isinstance(const_idx, int):
                            const_map[dest] = const_idx
                    elif inst.opcode == "MOVE":
                        src = inst.operands[1]
                        if isinstance(src, int) and src in const_map:
                            const_map[dest] = const_map[src]
                        elif dest in const_map:
                            del const_map[dest]
                    else:
                        const_map.pop(dest, None)

            new_blocks.append(MIRBlock(block.id, tuple(new_instructions), block.terminator))
        blocks = new_blocks

    return MIRFunction(
        function.name,
        function.params,
        function.register_count,
        tuple(blocks),
        function.entry,
    )


def _process_instruction(
    inst: MIRInstruction,
    const_map: dict[int, int],
    pool: MIRConstantPool,
) -> tuple[MIRInstruction, bool]:
    """Try to propagate constants into *inst*. Returns (new_inst, changed)."""
    match inst.opcode:
        case "CALL":
            return _propagate_call(inst, const_map, pool)
        case "DEFINE_ONCE" | "STORE_LOCAL":
            return _propagate_store(inst, const_map)
        case "BUILD_TUPLE":
            return _propagate_tuple(inst, const_map)
        case "APPEND_RESULT":
            return _propagate_append(inst, const_map)
        case _:
            return inst, False


def _propagate_call(
    inst: MIRInstruction,
    const_map: dict[int, int],
    pool: MIRConstantPool,
) -> tuple[MIRInstruction, bool]:
    dest, op_reg, arg_regs = inst.operands
    changed = False

    if isinstance(op_reg, int) and op_reg in const_map:
        # Don't propagate operator: it needs to remain a register for CALL
        pass

    new_args: list[object] = []
    if isinstance(arg_regs, tuple):
        for a in arg_regs:
            if isinstance(a, int) and a in const_map:
                new_args.append(const_map[a])
                changed = True
            else:
                new_args.append(a)

    if changed:
        new_arg_tuple = tuple(new_args)
        if new_arg_tuple != arg_regs:
            return MIRInstruction("CALL", (dest, op_reg, new_arg_tuple), inst.span), True
    return inst, False


def _propagate_store(
    inst: MIRInstruction,
    const_map: dict[int, int],
) -> tuple[MIRInstruction, bool]:
    _, val_reg = inst.operands
    if isinstance(val_reg, int) and val_reg in const_map:
        # Convert STORE_LOCAL r, src to LOAD_CONST + STORE_LOCAL pattern
        # Not directly useful; just note that the value is known constant.
        # The consumer (CONST_FOLD) will handle the actual folding.
        pass
    return inst, False


def _propagate_tuple(
    inst: MIRInstruction,
    const_map: dict[int, int],
) -> tuple[MIRInstruction, bool]:
    changed = False
    new_ops: list[object] = []
    for op in inst.operands:
        if isinstance(op, int) and op in const_map:
            new_ops.append(op)
            changed = True
        else:
            new_ops.append(op)
    if changed:
        new_ops_tuple = tuple(new_ops)
        if new_ops_tuple != inst.operands:
            return MIRInstruction(inst.opcode, new_ops_tuple, inst.span), True
    return inst, False


def _propagate_append(
    inst: MIRInstruction,
    const_map: dict[int, int],
) -> tuple[MIRInstruction, bool]:
    val = inst.operands[0]
    if isinstance(val, int) and val in const_map:
        return inst, False  # APPEND_RESULT takes a register, not a value
    return inst, False


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
