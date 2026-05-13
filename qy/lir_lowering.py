# coding: utf-8

from __future__ import annotations

from dataclasses import dataclass

from qy.lir import LIRFunction
from qy.lir import LIRInstruction
from qy.lir import LIRProgram
from qy.mir import MIRBlockId
from qy.mir import MIRFunction
from qy.mir import MIRProgram
from qy.mir import MIRTerminator
from qy.mir import verify_mir

__all__ = ["lower_lir"]


def lower_lir(program: MIRProgram) -> LIRProgram:
    verifier_diagnostics = verify_mir(program)
    diagnostics = (*program.diagnostics, *verifier_diagnostics)
    if any(d.severity == "error" for d in diagnostics):
        return LIRProgram((), 0, diagnostics)
    return LIRProgram(
        tuple(_lower_function(f) for f in program.functions),
        program.main,
        diagnostics,
    )


@dataclass(slots=True)
class _Patch:
    instruction_index: int
    target_block: MIRBlockId


def _lower_function(function: MIRFunction) -> LIRFunction:
    instructions: list[LIRInstruction] = []
    block_offsets: dict[MIRBlockId, int] = {}
    patches: list[_Patch] = []

    for block in function.blocks:
        block_offsets[block.id] = len(instructions)
        for instruction in block.instructions:
            instructions.append(
                LIRInstruction(instruction.opcode, instruction.operands, instruction.span)
            )
        _emit_terminator(block.terminator, instructions, patches)

    _patch_jumps(instructions, patches, block_offsets)
    return LIRFunction(
        function.name,
        function.params,
        function.register_count,
        tuple(instructions),
    )


def _emit_terminator(
    terminator: MIRTerminator,
    instructions: list[LIRInstruction],
    patches: list[_Patch],
) -> None:
    match terminator.opcode:
        case "RETURN":
            instructions.append(LIRInstruction("RETURN", terminator.operands, terminator.span))
        case "TAIL_CALL":
            instructions.append(LIRInstruction("TAIL_CALL", terminator.operands, terminator.span))
        case "JUMP":
            (target_block,) = terminator.operands
            patches.append(_Patch(len(instructions), _block_id(target_block)))
            instructions.append(LIRInstruction("JUMP", (None,), terminator.span))
        case "BRANCH":
            condition, true_block, false_block = terminator.operands
            patches.append(_Patch(len(instructions), _block_id(false_block)))
            instructions.append(LIRInstruction("JUMP_IF_FALSE", (condition, None), terminator.span))
            patches.append(_Patch(len(instructions), _block_id(true_block)))
            instructions.append(LIRInstruction("JUMP", (None,), terminator.span))
        case "RAISE_EFFECT":
            instructions.append(
                LIRInstruction("RAISE_EFFECT", terminator.operands, terminator.span)
            )


def _patch_jumps(
    instructions: list[LIRInstruction],
    patches: list[_Patch],
    block_offsets: dict[MIRBlockId, int],
) -> None:
    for patch in patches:
        instruction = instructions[patch.instruction_index]
        operands = (*instruction.operands[:-1], block_offsets[patch.target_block])
        instructions[patch.instruction_index] = LIRInstruction(
            instruction.opcode, operands, instruction.span
        )


def _block_id(value: object) -> MIRBlockId:
    if not isinstance(value, int):
        raise TypeError(f"expected MIR block id, got {value!r}")
    return value
