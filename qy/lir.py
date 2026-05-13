# coding: utf-8
"""LIR (Low-level IR): linearized instruction sequence ready for register VM.

LIR is MIR with the CFG flattened into a single instruction sequence per
function: basic block boundaries are removed and jump targets are resolved to
instruction offsets.  LIR shares the bytecode opcode set; the bytecode compiler
performs a structural-only conversion from LIR to BytecodeProgram.
"""

from __future__ import annotations

from dataclasses import dataclass

from qy.bytecode import Opcode
from qy.diagnostics import Diagnostic
from qy.errors import SourceSpan
from qy.reader import Symbol

__all__ = ["LIRFunction", "LIRInstruction", "LIRProgram", "dump_lir"]

LIROpcode = Opcode


@dataclass(frozen=True, slots=True)
class LIRInstruction:
    opcode: LIROpcode
    operands: tuple[object, ...] = ()
    span: SourceSpan | None = None


@dataclass(frozen=True, slots=True)
class LIRFunction:
    name: Symbol
    params: tuple[Symbol, ...]
    register_count: int
    instructions: tuple[LIRInstruction, ...]


@dataclass(frozen=True, slots=True)
class LIRProgram:
    functions: tuple[LIRFunction, ...]
    main: int = 0
    diagnostics: tuple[Diagnostic, ...] = ()

    @property
    def ok(self) -> bool:
        return not any(diagnostic.severity == "error" for diagnostic in self.diagnostics)


def dump_lir(program: LIRProgram) -> str:
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


def _format_instruction(instruction: LIRInstruction) -> str:
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
