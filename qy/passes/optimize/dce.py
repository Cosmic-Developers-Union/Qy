# coding: utf-8
"""optimize.dce pass。.

Eliminates dead code: instructions whose result register is never used
and whose opcode has no side effects.
"""

from __future__ import annotations

from qy.ir.mir import MIRBlock
from qy.ir.mir import MIRFunction
from qy.ir.mir import MIRInstruction
from qy.ir.mir import MIRProgram
from qy.ir.mir import MIRTerminator
from qy.passes.pass_base import Pass
from qy.passes.pass_base import PassContext
from qy.passes.pass_base import PassResult

__all__ = ["DCEPass"]

_SIDE_EFFECT_FREE: frozenset[str] = frozenset(
    {
        "LOAD_CONST",
        "LOAD_HOST",
        "LOAD_ENV",
        "MOVE",
        "MAKE_FUNCTION",
        "MAKE_MACRO",
        "BUILD_TUPLE",
    }
)


class DCEPass(Pass):
    def __init__(self):
        super().__init__("optimize.dce")

    def run(self, context: PassContext) -> PassResult:
        from typing import cast

        program = cast(MIRProgram, context.input_artifact)
        new_functions = tuple(_eliminate_dead(f) for f in program.functions)
        return PassResult(
            success=True,
            artifact=MIRProgram(
                new_functions, program.constants, program.main, program.diagnostics
            ),
        )


def _eliminate_dead(function: MIRFunction) -> MIRFunction:
    blocks = list(function.blocks)
    changed = True

    while changed:
        changed = False
        used = _collect_used_registers(blocks)

        new_blocks: list[MIRBlock] = []
        for block in blocks:
            new_instructions: list[MIRInstruction] = []
            for inst in block.instructions:
                if _is_dead(inst, used):
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


def _is_dead(inst: MIRInstruction, used: set[int]) -> bool:
    if inst.opcode not in _SIDE_EFFECT_FREE:
        return False
    if not inst.operands:
        return False
    dest = inst.operands[0]
    if not isinstance(dest, int):
        return False
    return dest not in used


def _collect_used_registers(blocks: list[MIRBlock]) -> set[int]:
    used: set[int] = set()
    for block in blocks:
        for inst in block.instructions:
            _collect_uses_from_instruction(inst, used)
        _collect_uses_from_terminator(block.terminator, used)
    return used


def _collect_uses_from_instruction(inst: MIRInstruction, used: set[int]) -> None:
    match inst.opcode:
        case "LOAD_CONST" | "LOAD_HOST" | "LOAD_ENV" | "LOAD_NIL" | "LOAD_T":
            pass
        case "MOVE":
            _add_reg(inst.operands[1], used)
        case "MAKE_FUNCTION" | "MAKE_MACRO":
            pass
        case "CALL":
            _, op_reg, arg_regs = inst.operands
            _add_reg(op_reg, used)
            if isinstance(arg_regs, tuple):
                for r in arg_regs:
                    _add_reg(r, used)
        case "APPLY":
            for op in inst.operands[1:]:
                _add_reg(op, used)
        case "DEFINE_ONCE":
            _add_reg(inst.operands[1], used)
        case "STORE_LOCAL":
            _add_reg(inst.operands[1], used)
        case "BUILD_TUPLE":
            for op in inst.operands[1:]:
                _add_reg(op, used)
        case "PERFORM":
            _add_reg(inst.operands[2], used)
        case "HANDLE":
            pass
        case "RESUME":
            for op in inst.operands[1:]:
                _add_reg(op, used)
        case "RUNTIME_EVAL":
            for op in inst.operands[1:]:
                _add_reg(op, used)
        case "CACHE_EVAL":
            pass
        case "APPEND_RESULT":
            _add_reg(inst.operands[0], used)
        case "PARALLEL_GATHER" | "ALL_GATHER" | "RACE_FIRST":
            pass
        case "DEFINE_MODULE":
            pass
        case "FROM_IMPORT":
            pass
        case _:
            for op in inst.operands:
                _add_reg(op, used)


def _collect_uses_from_terminator(term: MIRTerminator, used: set[int]) -> None:
    match term.opcode:
        case "RETURN":
            _add_reg(term.operands[0], used)
        case "TAIL_CALL":
            fn_reg, arg_regs = term.operands
            _add_reg(fn_reg, used)
            if isinstance(arg_regs, tuple):
                for r in arg_regs:
                    _add_reg(r, used)
        case "BRANCH":
            _add_reg(term.operands[0], used)
        case "RAISE_EFFECT":
            _add_reg(term.operands[1], used)
        case _:
            pass


def _add_reg(value: object, used: set[int]) -> None:
    if isinstance(value, int):
        used.add(value)
