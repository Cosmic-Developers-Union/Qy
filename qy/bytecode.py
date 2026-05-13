# coding: utf-8

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from typing import Literal

from qy.diagnostics import Diagnostic
from qy.errors import SourceSpan
from qy.reader import Symbol

if TYPE_CHECKING:
    from qy.evaluator import Environment

__all__ = [
    "BytecodeFunction",
    "BytecodeFunctionValue",
    "BytecodeProgram",
    "Instruction",
    "Opcode",
    "Register",
    "dump_bytecode",
]

Register = int

Opcode = Literal[
    "APPEND_RESULT",
    "CALL",
    "ENTER_SCOPE",
    "EXIT_SCOPE",
    "JUMP",
    "JUMP_IF_FALSE",
    "LOAD_CONST",
    "LOAD_ENV",
    "MAKE_MACRO",
    "MAKE_FUNCTION",
    "MOVE",
    "RETURN",
    "STORE_LOCAL",
    "TAIL_CALL",
]


@dataclass(frozen=True, slots=True)
class Instruction:
    opcode: Opcode
    operands: tuple[object, ...] = ()
    span: SourceSpan | None = None


@dataclass(frozen=True, slots=True)
class BytecodeFunction:
    name: Symbol
    params: tuple[Symbol, ...]
    register_count: int
    instructions: tuple[Instruction, ...]


@dataclass(frozen=True, slots=True)
class BytecodeProgram:
    functions: tuple[BytecodeFunction, ...]
    main: int = 0
    diagnostics: tuple[Diagnostic, ...] = ()

    @property
    def ok(self) -> bool:
        return not any(diagnostic.severity == "error" for diagnostic in self.diagnostics)


@dataclass(frozen=True, slots=True)
class BytecodeFunctionValue:
    function: BytecodeFunction
    closure: Environment


def dump_bytecode(program: BytecodeProgram) -> str:
    lines: list[str] = []
    for index, function in enumerate(program.functions):
        params = ", ".join(param.name for param in function.params)
        suffix = " [main]" if index == program.main else ""
        lines.append(
            f"fn#{index} {function.name.name}({params}) regs={function.register_count}{suffix}"
        )
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


def _format_instruction(instruction: Instruction) -> str:
    if not instruction.operands:
        return instruction.opcode
    return (
        f"{instruction.opcode} {', '.join(_format_operand(item) for item in instruction.operands)}"
    )


def _format_operand(value: object) -> str:
    if isinstance(value, Symbol):
        return value.name
    if isinstance(value, tuple):
        return f"({', '.join(_format_operand(item) for item in value)})"
    return repr(value)


def _format_span(span: SourceSpan | None) -> str:
    if span is None:
        return ""
    return f" @ {span.format()}"
