# coding: utf-8
from __future__ import annotations

from collections.abc import Callable

from qy.ir.lir import LIRInstruction

__all__ = ["compact_registers"]


def compact_registers(
    params: tuple[object, ...],
    instructions: list[LIRInstruction],
    register_count: int,
) -> tuple[list[LIRInstruction], int]:
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


def _operand_tuple(value: object) -> tuple[object, ...]:
    if not isinstance(value, tuple):
        raise TypeError(f"expected tuple operand, got {value!r}")
    return value


def _map_register_operands(
    opcode: str,
    operands: tuple[object, ...],
    map_register: Callable[[object], object],
) -> tuple[object, ...]:
    match opcode:
        case "LOAD_NIL" | "LOAD_T":
            return (map_register(operands[0]),)
        case "LOAD_INT" | "LOAD_FLOAT" | "LOAD_STR":
            return (map_register(operands[0]), operands[1])
        case "LOAD_HOST" | "LOAD_ENV":
            return (map_register(operands[0]), operands[1])
        case "SS_LOOKUP" | "SLOT_READ" | "SLOT_PENDING_EFFORT":
            return (map_register(operands[0]), *operands[1:])
        case "SLOT_COMPLETE":
            return (operands[0], map_register(operands[1]))
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
            return (map_register(operands[0]), operands[1], operands[2], operands[3])
        case "PERFORM":
            return (map_register(operands[0]), operands[1], map_register(operands[2]))
        case "HANDLE":
            return (map_register(operands[0]), operands[1], operands[2])
        case "JUMP_IF_FALSE":
            return (map_register(operands[0]), operands[1])
        case "RAISE_EFFECT":
            return (operands[0], map_register(operands[1]), operands[2])
        case "CONT_CAPTURE":
            live_registers = _operand_tuple(operands[3]) if len(operands) >= 4 else ()
            return (
                map_register(operands[0]),
                operands[1],
                operands[2],
                tuple(map_register(item) for item in live_registers),
            )
        case "CONT_COPY":
            return (map_register(operands[0]), map_register(operands[1]))
        case "CONT_RESTORE":
            return (map_register(operands[0]),)
        case "CONT_INJECT":
            return (map_register(operands[0]), map_register(operands[1]))
        case "EFFECT_UNWIND" | "EFFECT_DISPATCH":
            return tuple(map_register(item) for item in operands)
        case _:
            return operands
