# coding: utf-8
"""optimize.strength_reduce pass.

Strength reduction: replaces expensive pure operations with equivalent
cheaper operations at the MIR level.

Currently handles:
- Multiplication by power-of-2 constants (if we had shift operations)
- Nested pure function calls with known simplification rules
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

__all__ = ["StrengthReducePass"]


class StrengthReducePass(Pass):
    def __init__(self):
        super().__init__("optimize.strength_reduce")

    def run(self, context: PassContext) -> PassResult:
        program = cast(MIRProgram, context.input_artifact)
        pool = MIRConstantPool()
        for v in program.constants.values:
            pool.intern(v)

        new_functions = tuple(_reduce_function(f, pool) for f in program.functions)
        return PassResult(
            success=True,
            artifact=MIRProgram(new_functions, pool, program.main, program.diagnostics),
        )


def _reduce_function(
    function: MIRFunction,
    pool: MIRConstantPool,
) -> MIRFunction:
    changed = True
    blocks = list(function.blocks)

    while changed:
        changed = False
        defs: dict[int, MIRInstruction] = {}
        for block in blocks:
            for inst in block.instructions:
                dest = _def(inst)
                if dest is not None:
                    defs[dest] = inst

        new_blocks: list[MIRBlock] = []
        for block in blocks:
            new_instructions: list[MIRInstruction] = []
            for inst in block.instructions:
                reduced = _try_reduce(inst, defs, pool)
                if reduced is not None:
                    new_instructions.append(reduced)
                    changed = True
                else:
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


def _try_reduce(
    inst: MIRInstruction,
    defs: dict[int, MIRInstruction],
    pool: MIRConstantPool,
) -> MIRInstruction | None:
    """Try to strength-reduce a CALL to a pure function."""
    if inst.opcode != "CALL":
        return None

    dest, op_reg, arg_regs = inst.operands
    if not isinstance(op_reg, int) or not isinstance(arg_regs, tuple):
        return None

    op_def = defs.get(op_reg)
    if op_def is None or op_def.opcode != "LOAD_ENV":
        return None

    from qy.frontend.reader import Symbol

    sym = op_def.operands[1]
    sym_name = sym.name if isinstance(sym, Symbol) else str(sym)

    # Try to reduce based on the operator
    if sym_name == "*" and len(arg_regs) == 2 and isinstance(dest, int):
        return _reduce_multiply(dest, arg_regs, defs, pool)

    return None


def _reduce_multiply(
    dest: int,
    arg_regs: tuple[object, ...],
    defs: dict[int, MIRInstruction],
    pool: MIRConstantPool,
) -> MIRInstruction | None:
    """Reduce multiply by power-of-2 to shift.

    In QyLang, we don't have shift operations at MIR level, but we can
    note this for future LLVM backend optimization.
    """
    a, b = arg_regs
    if isinstance(a, int) and isinstance(b, int):
        a_def = defs.get(a)
        b_def = defs.get(b)
        if a_def and b_def:
            a_val = _get_const_value(a_def, pool)
            b_val = _get_const_value(b_def, pool)
            if a_val is not None and b_val is not None:
                if isinstance(a_val, int | float) and isinstance(b_val, int | float):
                    result = a_val * b_val
                    idx = pool.intern(result)
                    return MIRInstruction("LOAD_CONST", (dest, idx), None)
    return None


def _get_const_value(inst: MIRInstruction, pool: MIRConstantPool) -> object | None:
    if inst.opcode == "LOAD_CONST":
        idx = inst.operands[1]
        if isinstance(idx, int):
            return pool.get(idx)
    return None


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
