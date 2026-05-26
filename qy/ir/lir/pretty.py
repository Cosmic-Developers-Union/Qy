# -*- coding: utf-8 -*-
# Copyright (C) 2025 Cosmic-Developers-Union (CDU), All rights reserved.

"""LIR pretty printer 目标模块。.

目标：
- 为 CLI、debug、测试快照提供稳定 LIR dump。
- dump abstract-machine facts，而不暴露 Python 对象 repr 细节。

禁止：
- 不得在 pretty printer 中修正或解释 LIR 语义。
"""

from __future__ import annotations

from qy.errors import SourceSpan
from qy.frontend.reader import Symbol
from qy.ir.lir.frame import LIRContinuationLayout
from qy.ir.lir.frame import LIRFrameLayout
from qy.ir.lir.frame import LIRHandlerLayout
from qy.ir.lir.frame import LIRSymbolSpaceLayout
from qy.ir.lir.node import LIRBindingAddr
from qy.ir.lir.node import LIRInstruction
from qy.ir.lir.node import LIRProgram

__all__ = ["dump_lir"]


def dump_lir(program: LIRProgram) -> str:
    lines: list[str] = []
    if program.dialect != "compat":
        lines.append(f"dialect: {program.dialect}")
    for index, function in enumerate(program.functions):
        params = ", ".join(param.name for param in function.params)
        suffix = " [main]" if index == program.main else ""
        lines.append(
            f"fn#{index} {function.name.name}({params}) regs={function.register_count}{suffix}"
        )
        if function.frame_layout is not None:
            lines.append(f"  frame: {_format_frame_layout(function.frame_layout)}")
        for space in function.symbol_spaces:
            lines.append(f"  space: {_format_symbol_space(space)}")
        for continuation in function.continuations:
            lines.append(f"  continuation: {_format_continuation(continuation)}")
        for handler in function.handlers:
            lines.append(f"  handler: {_format_handler(handler)}")
        if not function.instructions:
            lines.append("  ; no instructions")
            continue
        for instruction_index, instruction in enumerate(function.instructions):
            lines.append(
                f"  {instruction_index:04d}: {_format_instruction(instruction)}{_format_span(instruction.span)}"
            )
    if program.diagnostics:
        lines.append("diagnostics:")
        lines.extend(
            f"  - {diagnostic.severity}: {diagnostic.message}" for diagnostic in program.diagnostics
        )
    return "\n".join(lines)


def _format_instruction(instruction: LIRInstruction) -> str:
    if not instruction.operands:
        return instruction.opcode
    return (
        f"{instruction.opcode} {', '.join(_format_operand(item) for item in instruction.operands)}"
    )


def _format_operand(value: object) -> str:
    if isinstance(value, LIRBindingAddr):
        return f"s{value.space}.slot{value.slot}"
    if isinstance(value, Symbol):
        return value.name
    if isinstance(value, tuple):
        return f"({', '.join(_format_operand(item) for item in value)})"
    return repr(value)


def _format_frame_layout(value: LIRFrameLayout) -> str:
    pieces = [
        value.kind,
        value.name,
        f"regs={value.register_count}",
        f"slots={value.local_slot_count}",
    ]
    if value.ss_chain:
        pieces.append(f"ss=({_format_int_tuple(value.ss_chain)})")
    if value.saved_registers:
        pieces.append(f"saved=({_format_int_tuple(value.saved_registers)})")
    return " ".join(pieces)


def _format_symbol_space(value: LIRSymbolSpaceLayout) -> str:
    parent = "" if value.parent is None else f" parent=s{value.parent}"
    slots = ", ".join(
        f"{slot.symbol.name}@slot{slot.address.slot}:{slot.state}" for slot in value.slots
    )
    return f"s{value.id} {value.name}{parent} slots=[{slots}]"


def _format_continuation(value: LIRContinuationLayout) -> str:
    target = "<unknown>" if value.resume_target is None else str(value.resume_target)
    spaces = _format_int_tuple(value.saved_spaces)
    regs = _format_int_tuple(value.saved_registers)
    mode = "multi-shot" if value.multi_shot else "one-shot"
    return f"k{value.id} target={target} spaces=({spaces}) regs=({regs}) {mode}"


def _format_handler(value: LIRHandlerLayout) -> str:
    target = "<unknown>" if value.handler_target is None else str(value.handler_target)
    effects = ", ".join(effect.name for effect in value.effects)
    spaces = _format_int_tuple(value.ss_chain)
    parent = "" if value.parent_handler is None else f" parent=h{value.parent_handler}"
    return f"h{value.id} effects=[{effects}] target={target} ss=({spaces}){parent}"


def _format_int_tuple(values: tuple[int, ...]) -> str:
    return ", ".join(str(item) for item in values)


def _format_span(span: SourceSpan | None) -> str:
    if span is None:
        return ""
    return f" @ {span.format()}"
