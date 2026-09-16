# coding: utf-8
"""optimize.const_fold pass。.

Folds calls to pure operators with all-constant arguments into constants.
"""

from __future__ import annotations

from dataclasses import replace
from typing import cast

from qy.core.operators import PureOperator
from qy.core.syntax import Symbol
from qy.ir.mir import MIRBlock
from qy.ir.mir import MIRConstantPool
from qy.ir.mir import MIRFunction
from qy.ir.mir import MIRInstruction
from qy.ir.mir import MIRProgram
from qy.passes.optimize.facts import rebuild_program
from qy.passes.optimize.facts import shadowed_names
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

        shadowed = shadowed_names(program)
        new_functions = tuple(
            _fold_function(f, pool, pure_ops, shadowed) for f in program.functions
        )
        return PassResult(
            success=True,
            artifact=rebuild_program(program, functions=new_functions, constants=pool),
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
    shadowed: frozenset[str],
) -> MIRFunction:
    if not pure_ops:
        return function

    changed = True
    blocks = list(function.blocks)

    while changed:
        changed = False
        # 只有在整个函数内**唯一**定义的寄存器才允许当作已知值：跨块"最后一次
        # 写"并不支配所有使用点，会误折叠。
        defs = _unique_definitions(blocks)

        new_blocks: list[MIRBlock] = []
        for block in blocks:
            new_instructions: list[MIRInstruction] = []
            for inst in block.instructions:
                folded = _try_fold(inst, defs, pool, pure_ops, shadowed)
                if folded is not None:
                    new_instructions.append(folded)
                    changed = True
                else:
                    new_instructions.append(inst)
            new_blocks.append(MIRBlock(block.id, tuple(new_instructions), block.terminator))
        blocks = new_blocks

    return replace(
        function,
        blocks=tuple(blocks),
        register_count=function.register_count,
    )


def _unique_definitions(blocks: list[MIRBlock]) -> dict[int, MIRInstruction]:
    """Reg -> 定义指令，仅当该寄存器在函数内只被定义一次。."""
    counts: dict[int, int] = {}
    defs: dict[int, MIRInstruction] = {}
    for block in blocks:
        for inst in block.instructions:
            if not inst.operands:
                continue
            dest = inst.operands[0]
            if not isinstance(dest, int) or not _defines(inst):
                continue
            counts[dest] = counts.get(dest, 0) + 1
            defs[dest] = inst
    return {reg: inst for reg, inst in defs.items() if counts[reg] == 1}


def _defines(inst: MIRInstruction) -> bool:
    return inst.opcode in (
        "LOAD_CONST",
        "LOAD_HOST",
        "LOAD_ENV",
        "MOVE",
        "CALL",
        "APPLY",
        "BUILD_TUPLE",
        "MAKE_FUNCTION",
        "MAKE_MACRO",
        "RUNTIME_EVAL",
        "CACHE_EVAL",
        "PARALLEL_GATHER",
        "ALL_GATHER",
        "RACE_FIRST",
        "LOAD_NIL",
        "LOAD_T",
    )


def _try_fold(
    inst: MIRInstruction,
    defs: dict[int, MIRInstruction],
    pool: MIRConstantPool,
    pure_ops: dict[str, PureOperator],
    shadowed: frozenset[str],
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
    # 被 define/let/from shadow 的名字在运行时不指向内置算子，禁止折叠。
    if sym_name in shadowed:
        return None
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
