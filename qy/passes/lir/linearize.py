# coding: utf-8
from __future__ import annotations

from dataclasses import dataclass

from qy.ir.lir import LIRInstruction
from qy.ir.mir import MIRBlockId
from qy.ir.mir import MIRConstantPool
from qy.ir.mir import MIRFunction
from qy.ir.mir import MIRInstruction
from qy.ir.mir import MIRTerminator

__all__ = ["linearize_function"]


@dataclass(slots=True)
class _Patch:
    instruction_index: int
    target_block: MIRBlockId


def linearize_function(function: MIRFunction, constants: MIRConstantPool) -> list[LIRInstruction]:
    instructions: list[LIRInstruction] = []
    block_offsets: dict[MIRBlockId, int] = {}
    patches: list[_Patch] = []

    for block in function.blocks:
        block_offsets[block.id] = len(instructions)
        for instruction in block.instructions:
            lowered = _lower_instruction(instruction, constants)
            instructions.append(lowered)
        _emit_terminator(block.terminator, instructions, patches)

    _patch_jumps(instructions, patches, block_offsets)
    return instructions


def _lower_instruction(instruction: MIRInstruction, constants: MIRConstantPool) -> LIRInstruction:
    if instruction.opcode == "LOAD_CONST":
        dest, idx = instruction.operands
        value = constants.get(idx)  # ty: ignore[invalid-argument-type]
        return LIRInstruction("LOAD_HOST", (dest, value), instruction.span)
    return LIRInstruction(instruction.opcode, instruction.operands, instruction.span)


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
        case "EFFECT_PERFORM":
            # MIR EFFECT_PERFORM(dst, eff, arg, resume_block, resumable) →
            # LIR placeholder EFFECT_PERFORM(dst, eff, arg, resume_idx, resumable)
            # (instruction-index for resume_idx is patched after linearization).
            dst, effect_sym, arg_reg, resume_block, resumable = terminator.operands
            patches.append(_Patch(len(instructions), _block_id(resume_block)))
            instructions.append(
                LIRInstruction(
                    "EFFECT_PERFORM",
                    (dst, effect_sym, arg_reg, None, resumable),
                    terminator.span,
                )
            )


def _patch_jumps(
    instructions: list[LIRInstruction],
    patches: list[_Patch],
    block_offsets: dict[MIRBlockId, int],
) -> None:
    for patch in patches:
        instruction = instructions[patch.instruction_index]
        target = block_offsets[patch.target_block]
        if instruction.opcode == "EFFECT_PERFORM":
            # operand layout: (dst, eff, arg, resume_idx, resumable)
            ops = list(instruction.operands)
            ops[3] = target
            operands = tuple(ops)
        else:
            operands = (*instruction.operands[:-1], target)
        instructions[patch.instruction_index] = LIRInstruction(
            instruction.opcode, operands, instruction.span
        )


def _block_id(value: object) -> MIRBlockId:
    if not isinstance(value, int):
        raise TypeError(f"expected MIR block id, got {value!r}")
    return value
