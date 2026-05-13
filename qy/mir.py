"""Mid-level IR for the bytecode pipeline.

MIR uses virtual registers instead of SSA values.
Each basic block contains zero or more instructions followed by exactly one
terminator, and tail calls are modeled as terminators so control flow remains
explicit for later bytecode lowering.
"""

# coding: utf-8

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from qy.diagnostics import Diagnostic
from qy.errors import SourceSpan
from qy.reader import Symbol

__all__ = [
    "MIRBlock",
    "MIRBlockId",
    "MIRFunction",
    "MIRInstruction",
    "MIROpcode",
    "MIRProgram",
    "MIRRegister",
    "MIRTerminator",
    "MIRTerminatorOpcode",
    "dump_mir",
    "verify_mir",
]

MIRRegister = int
MIRBlockId = int

MIROpcode = Literal[
    "APPEND_RESULT",
    "CALL",
    "ENTER_SCOPE",
    "EXIT_SCOPE",
    "LOAD_CONST",
    "LOAD_ENV",
    "MAKE_FUNCTION",
    "MAKE_MACRO",
    "MOVE",
    "STORE_LOCAL",
]

MIRTerminatorOpcode = Literal["BRANCH", "JUMP", "RETURN", "TAIL_CALL"]


@dataclass(frozen=True, slots=True)
class MIRInstruction:
    opcode: MIROpcode
    operands: tuple[object, ...] = ()
    span: SourceSpan | None = None


@dataclass(frozen=True, slots=True)
class MIRTerminator:
    opcode: MIRTerminatorOpcode
    operands: tuple[object, ...] = ()
    span: SourceSpan | None = None


@dataclass(frozen=True, slots=True)
class MIRBlock:
    id: MIRBlockId
    instructions: tuple[MIRInstruction, ...]
    terminator: MIRTerminator


@dataclass(frozen=True, slots=True)
class MIRFunction:
    name: Symbol
    params: tuple[Symbol, ...]
    register_count: int
    blocks: tuple[MIRBlock, ...]
    entry: MIRBlockId = 0


@dataclass(frozen=True, slots=True)
class MIRProgram:
    functions: tuple[MIRFunction, ...]
    main: int = 0
    diagnostics: tuple[Diagnostic, ...] = ()

    @property
    def ok(self) -> bool:
        return not any(diagnostic.severity == "error" for diagnostic in self.diagnostics)


def verify_mir(program: MIRProgram) -> tuple[Diagnostic, ...]:
    diagnostics: list[Diagnostic] = []
    if not 0 <= program.main < len(program.functions):
        diagnostics.append(
            Diagnostic(
                f"main function index {program.main} is out of range for {len(program.functions)} MIR functions"
            )
        )
    for function in program.functions:
        _verify_function(function, diagnostics)
    return tuple(diagnostics)


def dump_mir(program: MIRProgram) -> str:
    sections = [
        _dump_mir_function(index, function, is_main=index == program.main)
        for index, function in enumerate(program.functions)
    ]
    if program.diagnostics:
        diagnostics = ["diagnostics:"]
        diagnostics.extend(
            f"  - {diagnostic.severity}: {diagnostic.message}" for diagnostic in program.diagnostics
        )
        sections.append("\n".join(diagnostics))
    return "\n\n".join(sections)


def _verify_function(function: MIRFunction, diagnostics: list[Diagnostic]) -> None:
    if function.register_count < 0:
        diagnostics.append(
            Diagnostic(f"function {function.name.name!r} has negative register_count")
        )
        return

    block_ids: set[MIRBlockId] = set()
    for block in function.blocks:
        if block.id in block_ids:
            diagnostics.append(
                Diagnostic(f"function {function.name.name!r} defines duplicate block bb{block.id}")
            )
            continue
        block_ids.add(block.id)

    if function.entry not in block_ids:
        diagnostics.append(
            Diagnostic(
                f"function {function.name.name!r} entry block bb{function.entry} does not exist"
            )
        )

    for block in function.blocks:
        if block.terminator is None:
            diagnostics.append(
                Diagnostic(
                    f"function {function.name.name!r} block bb{block.id} is missing a terminator"
                )
            )
            continue

        for instruction in block.instructions:
            if instruction.opcode == "TAIL_CALL":
                diagnostics.append(
                    Diagnostic(
                        f"function {function.name.name!r} block bb{block.id} uses TAIL_CALL as a non-terminator instruction"
                    )
                )
            for register in _instruction_registers(instruction):
                _check_register(function, block.id, register, diagnostics)

        for target in _terminator_targets(block.terminator):
            if not isinstance(target, int):
                diagnostics.append(
                    Diagnostic(
                        f"function {function.name.name!r} block bb{block.id} jumps to non-block target {target!r}"
                    )
                )
                continue
            if target not in block_ids:
                diagnostics.append(
                    Diagnostic(
                        f"function {function.name.name!r} block bb{block.id} jumps to missing block bb{target}"
                    )
                )

        for register in _terminator_registers(block.terminator):
            _check_register(function, block.id, register, diagnostics)


def _instruction_registers(instruction: MIRInstruction) -> tuple[object, ...]:
    operands = instruction.operands
    match instruction.opcode:
        case "APPEND_RESULT":
            return (operands[0],)
        case "CALL":
            return (operands[0], operands[1], *_operand_tuple(operands[2]))
        case "LOAD_CONST" | "LOAD_ENV" | "MAKE_FUNCTION" | "MAKE_MACRO":
            return (operands[0],)
        case "MOVE":
            return (operands[0], operands[1])
        case "STORE_LOCAL":
            return (operands[1],)
        case "ENTER_SCOPE" | "EXIT_SCOPE":
            return ()
    return ()


def _terminator_targets(terminator: MIRTerminator) -> tuple[object, ...]:
    operands = terminator.operands
    match terminator.opcode:
        case "JUMP":
            return (operands[0],)
        case "BRANCH":
            return (operands[1], operands[2])
        case "RETURN" | "TAIL_CALL":
            return ()
    return ()


def _terminator_registers(terminator: MIRTerminator) -> tuple[object, ...]:
    operands = terminator.operands
    match terminator.opcode:
        case "BRANCH":
            return (operands[0],)
        case "RETURN":
            return () if operands[0] is None else (operands[0],)
        case "TAIL_CALL":
            return (operands[0], *_operand_tuple(operands[1]))
        case "JUMP":
            return ()
    return ()


def _operand_tuple(value: object) -> tuple[object, ...]:
    return value if isinstance(value, tuple) else ()


def _check_register(
    function: MIRFunction,
    block_id: MIRBlockId,
    value: object,
    diagnostics: list[Diagnostic],
) -> None:
    if not isinstance(value, int):
        diagnostics.append(
            Diagnostic(
                f"function {function.name.name!r} block bb{block_id} references non-register operand {value!r} where a register is required"
            )
        )
        return
    if not 0 <= value < function.register_count:
        diagnostics.append(
            Diagnostic(
                f"function {function.name.name!r} block bb{block_id} references out-of-range register r{value} with register_count={function.register_count}"
            )
        )


def _dump_mir_function(index: int, function: MIRFunction, *, is_main: bool) -> str:
    params = ", ".join(param.name for param in function.params)
    suffix = " [main]" if is_main else ""
    lines = [
        f"fn#{index} {function.name.name}({params}) entry=bb{function.entry} regs={function.register_count}{suffix}"
    ]
    for block in function.blocks:
        lines.append(f"  bb{block.id}:")
        if not block.instructions:
            lines.append("    ; no instructions")
        else:
            lines.extend(
                f"    {_format_instruction(instruction)}" for instruction in block.instructions
            )
        lines.append(f"    {_format_terminator(block.terminator)}")
    return "\n".join(lines)


def _format_instruction(instruction: MIRInstruction) -> str:
    operands = instruction.operands
    match instruction.opcode:
        case "APPEND_RESULT":
            rendered = f"APPEND_RESULT {_format_register(operands[0])}"
        case "CALL":
            rendered = (
                f"{_format_register(operands[0])} = CALL {_format_register(operands[1])} "
                f"{_format_operand(operands[2])}"
            )
        case "ENTER_SCOPE" | "EXIT_SCOPE":
            rendered = instruction.opcode
        case "LOAD_CONST":
            rendered = (
                f"{_format_register(operands[0])} = LOAD_CONST {_format_operand(operands[1])}"
            )
        case "LOAD_ENV":
            rendered = f"{_format_register(operands[0])} = LOAD_ENV {_format_operand(operands[1])}"
        case "MAKE_FUNCTION":
            rendered = f"{_format_register(operands[0])} = MAKE_FUNCTION fn#{operands[1]}"
        case "MAKE_MACRO":
            rendered = (
                f"{_format_register(operands[0])} = MAKE_MACRO {_format_operand(operands[1])} "
                f"{_format_operand(operands[2])} {_format_operand(operands[3])}"
            )
        case "MOVE":
            rendered = f"{_format_register(operands[0])} = MOVE {_format_register(operands[1])}"
        case "STORE_LOCAL":
            rendered = (
                f"STORE_LOCAL {_format_operand(operands[0])}, {_format_register(operands[1])}"
            )
        case _:
            rendered = _format_generic(instruction.opcode, operands)
    return rendered + _format_span(instruction.span)


def _format_terminator(terminator: MIRTerminator) -> str:
    operands = terminator.operands
    match terminator.opcode:
        case "BRANCH":
            rendered = f"BRANCH {_format_register(operands[0])} ? bb{operands[1]} : bb{operands[2]}"
        case "JUMP":
            rendered = f"JUMP bb{operands[0]}"
        case "RETURN":
            rendered = f"RETURN {_format_operand(operands[0])}"
        case "TAIL_CALL":
            rendered = f"TAIL_CALL {_format_register(operands[0])} {_format_operand(operands[1])}"
        case _:
            rendered = _format_generic(terminator.opcode, operands)
    return rendered + _format_span(terminator.span)


def _format_register(value: object) -> str:
    return f"r{value}"


def _format_operand(value: object) -> str:
    if isinstance(value, Symbol):
        return value.name
    if isinstance(value, tuple):
        return f"({', '.join(_format_operand(item) for item in value)})"
    return repr(value)


def _format_generic(opcode: str, operands: tuple[object, ...]) -> str:
    if not operands:
        return opcode
    return f"{opcode} {', '.join(_format_operand(operand) for operand in operands)}"


def _format_span(span: SourceSpan | None) -> str:
    if span is None:
        return ""
    return f" @ {span.format()}"
