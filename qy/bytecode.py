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
