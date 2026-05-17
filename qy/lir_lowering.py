# coding: utf-8

from __future__ import annotations

from collections.abc import Callable
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
    instructions = _peephole(instructions)
    instructions, register_count = _layout_registers(
        function.params,
        instructions,
        function.register_count,
    )
    return LIRFunction(
        function.name,
        function.params,
        register_count,
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


def _peephole(instructions: list[LIRInstruction]) -> list[LIRInstruction]:
    """Remove obviously redundant instruction patterns.

    Currently handles:
    - MOVE r, r  (no-op self-assignment)
    """
    result = list(instructions)
    changed = True
    while changed:
        changed = False
        out: list[LIRInstruction] = []
        for instruction in result:
            # Eliminate MOVE r, r (no-op self-assignment)
            if instruction.opcode == "MOVE" and instruction.operands[0] == instruction.operands[1]:
                changed = True
                continue
            out.append(instruction)
        result = out
    return result


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


def _operand_tuple(value: object) -> tuple[object, ...]:
    if not isinstance(value, tuple):
        raise TypeError(f"expected tuple operand, got {value!r}")
    return value


def _layout_registers(
    params: tuple[object, ...],
    instructions: list[LIRInstruction],
    register_count: int,
) -> tuple[list[LIRInstruction], int]:
    # Keep parameter ABI stable and remap body temporaries into a compact register space.
    register_map: dict[int, int] = {index: index for index, _ in enumerate(params)}
    next_register = len(register_map)

    def map_register(value: object) -> object:
        nonlocal next_register
        if not isinstance(value, int):
            return value
        mapped = register_map.get(value)
        if mapped is not None:
            return mapped
        mapped = next_register
        register_map[value] = mapped
        next_register += 1
        return mapped

    remapped: list[LIRInstruction] = []
    for instruction in instructions:
        remapped.append(
            LIRInstruction(
                instruction.opcode,
                _map_register_operands(instruction.opcode, instruction.operands, map_register),
                instruction.span,
            )
        )

    compact_count = max(next_register, len(params))
    return remapped, compact_count


def _map_register_operands(
    opcode: str,
    operands: tuple[object, ...],
    map_register: Callable[[object], object],
) -> tuple[object, ...]:
    match opcode:
        case "LOAD_HOST" | "LOAD_ENV":
            return (map_register(operands[0]), operands[1])
        case "MOVE":
            return (map_register(operands[0]), map_register(operands[1]))
        case "DEFINE_ONCE":
            return (operands[0], map_register(operands[1]))
        case "MAKE_FUNCTION":
            return (map_register(operands[0]), operands[1])
        case "MAKE_MACRO":
            return (map_register(operands[0]), *operands[1:])
        case "CALL":
            arg_registers = _operand_tuple(operands[2])
            return (
                map_register(operands[0]),
                map_register(operands[1]),
                tuple(map_register(item) for item in arg_registers),
            )
        case "TAIL_CALL":
            arg_registers = _operand_tuple(operands[1])
            return (
                map_register(operands[0]),
                tuple(map_register(item) for item in arg_registers),
            )
        case "RETURN" | "APPEND_RESULT":
            return (map_register(operands[0]),)
        case "BUILD_TUPLE":
            return (map_register(operands[0]), *(map_register(item) for item in operands[1:]))
        case "APPLY" | "RUNTIME_EVAL" | "RESUME":
            return tuple(map_register(item) for item in operands)
        case "PARALLEL_GATHER" | "ALL_GATHER" | "RACE_FIRST":
            return (map_register(operands[0]), *operands[1:])
        case "CACHE_EVAL":
            return (map_register(operands[0]), operands[1], operands[2])
        case "DEFINE_MODULE":
            return (map_register(operands[0]), operands[1], operands[2])
        case "PERFORM":
            return (map_register(operands[0]), operands[1], map_register(operands[2]))
        case "HANDLE":
            return (map_register(operands[0]), operands[1], operands[2])
        case "JUMP_IF_FALSE":
            return (map_register(operands[0]), operands[1])
        case "RAISE_EFFECT":
            return (operands[0], map_register(operands[1]), operands[2])
        case _:
            return operands
