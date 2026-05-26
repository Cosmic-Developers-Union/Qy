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
        case "APPLY" | "RUNTIME_EVAL":
            return tuple(map_register(item) for item in operands)
        case "PARALLEL_GATHER" | "ALL_GATHER" | "RACE_FIRST":
            return (map_register(operands[0]), *operands[1:])
        case "CACHE_EVAL":
            return (map_register(operands[0]), operands[1], operands[2])
        case "DEFINE_MODULE":
            return (map_register(operands[0]), operands[1], operands[2], operands[3])
        case "JUMP_IF_FALSE":
            return (map_register(operands[0]), operands[1])
        case "RAISE_EFFECT":
            return (operands[0], map_register(operands[1]), operands[2])
        case "CONT_CAPTURE":
            # operands: (dst_cont_reg, cont_layout_id, resume_target_idx,
            #            saved_regs_tuple, dst_reg_for_resume, multi_shot)
            live_registers = _operand_tuple(operands[3]) if len(operands) >= 4 else ()
            dst_after = (
                map_register(operands[4])
                if len(operands) >= 5 and isinstance(operands[4], int)
                else (operands[4] if len(operands) >= 5 else None)
            )
            multi_shot = operands[5] if len(operands) >= 6 else True
            return (
                map_register(operands[0]),
                operands[1],
                operands[2],
                tuple(map_register(item) for item in live_registers),
                dst_after,
                multi_shot,
            )
        case "CONT_COPY":
            return (map_register(operands[0]), map_register(operands[1]))
        case "CONT_RESTORE":
            # operands: (cont_reg, dst_reg_after_resume, value_reg)
            return tuple(map_register(item) for item in operands[:3])
        case "CONT_INJECT":
            return (map_register(operands[0]), map_register(operands[1]))
        case "EFFECT_UNWIND":
            # operands: (effect_sym, arg_reg, cont_reg)
            return (
                operands[0],
                map_register(operands[1]),
                map_register(operands[2]),
            )
        case "EFFECT_DISPATCH":
            # operands: (dst_handler_fn_reg, handler_id, arg_dst_reg, cont_dst_reg)
            return (
                map_register(operands[0]),
                operands[1],
                map_register(operands[2]),
                map_register(operands[3]),
            )
        case "HANDLER_PUSH" | "HANDLER_POP":
            return operands
        case "FRAME_ENTER" | "FRAME_LEAVE":
            return operands
        case "SS_ENTER" | "SS_LEAVE" | "SS_RESTORE" | "SS_COPY":
            return operands
        case "EFFECT_PERFORM":
            # placeholder: (dst_reg, effect_sym, arg_reg, resume_idx, resumable)
            return (
                map_register(operands[0]),
                operands[1],
                map_register(operands[2]),
                operands[3],
                operands[4],
            )
        case "EFFECT_HANDLE_BEGIN":
            # placeholder: (handle_id, body_fn_idx, handler_specs); no registers.
            return operands
        case "EFFECT_HANDLE_END":
            # placeholder: (handle_id, dst_reg)
            return (operands[0], map_register(operands[1]))
        case "EFFECT_RESUME":
            return tuple(map_register(item) for item in operands[:3])
        case _:
            return operands
