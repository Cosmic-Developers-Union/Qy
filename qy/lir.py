# coding: utf-8
"""LIR (Low-level IR): linearized instruction sequence ready for register VM.

LIR is a low-level IR with its own opcode vocabulary, independent from bytecode.
It represents instructions after selection, scheduling, and register layout.
The bytecode compiler performs a structural mapping from LIR opcodes to bytecode
opcodes; LIR is free to express concepts bytecode cannot (e.g., LOAD_NIL).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from qy.diagnostics import Diagnostic
from qy.errors import SourceSpan
from qy.reader import Symbol

__all__ = [
    "LIRFunction",
    "LIRInstruction",
    "LIROpcode",
    "LIRProgram",
    "dump_lir",
    "verify_lir",
]

# LIR has its own opcode vocabulary.  Some opcodes overlap with bytecode for
# simplicity, but LIR is free to add opcodes that have no direct bytecode
# equivalent (LOAD_NIL, LOAD_T, BRANCH_NIL).  The bytecode compiler maps
# LIR opcodes to bytecode opcodes during encoding.
LIROpcode = Literal[
    # -- Value loading --
    "LOAD_HOST",  # load arbitrary host value
    "LOAD_NIL",  # load QY_NIL (peephole from LOAD_HOST None)
    "LOAD_T",  # load QY_T
    "LOAD_ENV",  # load from environment by symbol
    "MOVE",  # register-to-register copy
    # -- Storage --
    "STORE_LOCAL",  # store into local scope
    "DEFINE_ONCE",  # define-once binding
    # -- Function construction --
    "MAKE_FUNCTION",  # create function value from index
    "MAKE_MACRO",  # create macro (compile-time only)
    # -- Scope --
    "ENTER_SCOPE",
    "EXIT_SCOPE",
    # -- Results --
    "APPEND_RESULT",
    # -- Data construction --
    "BUILD_TUPLE",
    # -- Calls --
    "CALL",  # non-tail call
    "TAIL_CALL",  # tail call (frame replacement)
    "APPLY",  # dynamic apply
    # -- Control flow --
    "JUMP",
    "JUMP_IF_FALSE",  # branch on _truthy (nil-only)
    "BRANCH_NIL",  # branch specifically on QY_NIL check (LIR-specific)
    "RETURN",
    # -- Effects --
    "DEFEFFECT",
    "PERFORM",
    "HANDLE",
    "RESUME",
    "RAISE_EFFECT",
    # -- Concurrency --
    "PARALLEL_GATHER",
    "ALL_GATHER",
    "RACE_FIRST",
    "CACHE_EVAL",
    # -- Module --
    "DEFINE_MODULE",
    "FROM_IMPORT",
    # -- Meta --
    "RUNTIME_EVAL",
]


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


def verify_lir(program: LIRProgram) -> tuple[Diagnostic, ...]:
    """Basic structural verification of LIR program."""
    diagnostics: list[Diagnostic] = []
    for func in program.functions:
        if not func.instructions and func.name.name not in ("<lambda>",):
            diagnostics.append(
                Diagnostic(f"LIR function {func.name.name} has no instructions", severity="warning")
            )
        for idx, inst in enumerate(func.instructions):
            if inst.opcode == "LOAD_HOST" and len(inst.operands) >= 2 and inst.operands[1] is None:
                diagnostics.append(
                    Diagnostic(
                        f"LIR LOAD_HOST None at {func.name.name}:{idx} should be LOAD_NIL",
                        severity="warning",
                    )
                )
    return tuple(diagnostics)


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
