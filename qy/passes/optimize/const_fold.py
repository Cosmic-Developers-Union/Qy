# coding: utf-8
"""optimize.const_fold pass。.

Folds calls to pure operators with all-constant arguments into constants.
"""

from __future__ import annotations

from typing import cast

from qy.core.operators import PureOperator
from qy.frontend.reader import Symbol
from qy.ir.mir import MIRBlock
from qy.ir.mir import MIRConstantPool
from qy.ir.mir import MIRFunction
from qy.ir.mir import MIRInstruction
from qy.ir.mir import MIRProgram
from qy.passes.pass_base import Pass
from qy.passes.pass_base import PassContext
from qy.passes.pass_base import PassResult

__all__ = ["ConstFoldPass"]


class ConstFoldPass(Pass):
    def __init__(self):
        super().__init__("optimize.const_fold")

    def run(self, context: PassContext) -> PassResult:
        program = cast(MIRProgram, context.input_artifact)
        env = context.session.env
        pure_ops = _collect_pure_ops(env)
        pool = MIRConstantPool()
        for v in program.constants.values:
            pool.intern(v)

        new_functions = tuple(_fold_function(f, pool, pure_ops) for f in program.functions)
        return PassResult(
            success=True,
            artifact=MIRProgram(new_functions, pool, program.main, program.diagnostics),
        )


def _collect_pure_ops(env: object | None) -> dict[str, PureOperator]:
    if env is None:
        return {}
    from qy.session.runtime_space import Environment

    if not isinstance(env, Environment):
        return {}
    result: dict[str, PureOperator] = {}
    for sym, val in env.bindings().items():
        if isinstance(val, PureOperator) and val.argument_evaluator is None:
            result[sym.name if isinstance(sym, Symbol) else str(sym)] = val
    return result


def _fold_function(
    function: MIRFunction,
    pool: MIRConstantPool,
    pure_ops: dict[str, PureOperator],
) -> MIRFunction:
    if not pure_ops:
        return function

    changed = True
    blocks = list(function.blocks)

    while changed:
        changed = False
        defs: dict[int, MIRInstruction] = {}
        for block in blocks:
            for inst in block.instructions:
                if inst.operands:
                    defs[cast(int, inst.operands[0])] = inst

        new_blocks: list[MIRBlock] = []
        for block in blocks:
            new_instructions: list[MIRInstruction] = []
            for inst in block.instructions:
                folded = _try_fold(inst, defs, pool, pure_ops)
                if folded is not None:
                    new_instructions.append(folded)
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


def _try_fold(
    inst: MIRInstruction,
    defs: dict[int, MIRInstruction],
    pool: MIRConstantPool,
    pure_ops: dict[str, PureOperator],
) -> MIRInstruction | None:
    if inst.opcode != "CALL":
        return None

    dest, op_reg, arg_regs = inst.operands
    if not isinstance(arg_regs, tuple):
        return None

    from typing import cast

    op_def = defs.get(cast(int, op_reg))
    if op_def is None or op_def.opcode != "LOAD_ENV":
        return None

    sym = op_def.operands[1]
    sym_name = sym.name if isinstance(sym, Symbol) else str(sym)
    operator = pure_ops.get(sym_name)
    if operator is None:
        return None

    arg_values: list[object] = []
    for arg_reg in arg_regs:
        arg_def = defs.get(cast(int, arg_reg))
        if arg_def is None or arg_def.opcode != "LOAD_CONST":
            return None
        _, const_idx = arg_def.operands
        arg_values.append(pool.get(cast(int, const_idx)))

    try:
        result = operator.func(*arg_values)
    except Exception:
        return None

    new_idx = pool.intern(result)
    return MIRInstruction("LOAD_CONST", (dest, new_idx), inst.span)
