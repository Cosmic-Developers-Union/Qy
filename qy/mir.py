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
            return f"APPEND_RESULT {_format_register(operands[0])}"
        case "CALL":
            return (
                f"{_format_register(operands[0])} = CALL {_format_register(operands[1])} "
                f"{_format_operand(operands[2])}"
            )
        case "ENTER_SCOPE" | "EXIT_SCOPE":
            return instruction.opcode
        case "LOAD_CONST":
            return f"{_format_register(operands[0])} = LOAD_CONST {_format_operand(operands[1])}"
        case "LOAD_ENV":
            return f"{_format_register(operands[0])} = LOAD_ENV {_format_operand(operands[1])}"
        case "MAKE_FUNCTION":
            return f"{_format_register(operands[0])} = MAKE_FUNCTION fn#{operands[1]}"
        case "MAKE_MACRO":
            return (
                f"{_format_register(operands[0])} = MAKE_MACRO {_format_operand(operands[1])} "
                f"{_format_operand(operands[2])} {_format_operand(operands[3])}"
            )
        case "MOVE":
            return f"{_format_register(operands[0])} = MOVE {_format_register(operands[1])}"
        case "STORE_LOCAL":
            return f"STORE_LOCAL {_format_operand(operands[0])}, {_format_register(operands[1])}"
    return _format_generic(instruction.opcode, operands)


def _format_terminator(terminator: MIRTerminator) -> str:
    operands = terminator.operands
    match terminator.opcode:
        case "BRANCH":
            return f"BRANCH {_format_register(operands[0])} ? bb{operands[1]} : bb{operands[2]}"
        case "JUMP":
            return f"JUMP bb{operands[0]}"
        case "RETURN":
            return f"RETURN {_format_operand(operands[0])}"
        case "TAIL_CALL":
            return f"TAIL_CALL {_format_register(operands[0])} {_format_operand(operands[1])}"
    return _format_generic(terminator.opcode, operands)


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
