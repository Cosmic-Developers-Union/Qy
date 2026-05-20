# coding: utf-8
"""MIR node definitions — CFG / virtual-register IR types.

Contains: type aliases, opcode literals, and dataclass node definitions.
Verifier and pretty-printer live in the package __init__.
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from typing import Literal

from qy.diag import Diagnostic
from qy.errors import SourceSpan
from qy.reader import Symbol

__all__ = [
    "MIRBlock",
    "MIRBlockId",
    "MIRConstantPool",
    "MIRFunction",
    "MIRInstruction",
    "MIROpcode",
    "MIRProgram",
    "MIRRegister",
    "MIRTerminator",
    "MIRTerminatorOpcode",
]

MIRRegister = int
MIRBlockId = int

MIROpcode = Literal[
    "APPEND_RESULT",
    "ALL_GATHER",
    "APPLY",
    "BUILD_TUPLE",
    "CACHE_EVAL",
    "CALL",
    "DEFEFFECT",
    "DEFINE_MODULE",
    "DEFINE_ONCE",
    "ENTER_SCOPE",
    "EXIT_SCOPE",
    "FROM_IMPORT",
    "HANDLE",
    "LOAD_CONST",
    "LOAD_HOST",
    "LOAD_ENV",
    "MAKE_FUNCTION",
    "MAKE_MACRO",
    "MOVE",
    "PARALLEL_GATHER",
    "PERFORM",
    "RACE_FIRST",
    "RESUME",
    "RUNTIME_EVAL",
    "STORE_LOCAL",
]

MIRTerminatorOpcode = Literal["BRANCH", "JUMP", "RAISE_EFFECT", "RETURN", "TAIL_CALL"]


@dataclass(slots=True)
class MIRConstantPool:
    """Constant pool for MIR: stores Python objects referenced by index.

    Same value always gets the same index (interning).  This makes MIR
    serialisable and portable -- instructions reference constants by integer
    index instead of embedding Python objects directly.
    """

    _values: list[object]
    _index: dict[object, int]

    def __init__(self) -> None:
        self._values = []
        self._index = {}

    def intern(self, value: object) -> int:
        """Insert *value* into the pool and return its index.

        Each call always produces a fresh index — no deduplication.
        This preserves identity semantics for values like Symbols.
        """
        idx = len(self._values)
        self._values.append(value)
        return idx

    def get(self, index: int) -> object:
        """Return the constant at *index*."""
        return self._values[index]

    @property
    def values(self) -> tuple[object, ...]:
        return tuple(self._values)


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
    constants: MIRConstantPool = field(default_factory=MIRConstantPool)
    main: int = 0
    diagnostics: tuple[Diagnostic, ...] = ()

    @property
    def ok(self) -> bool:
        return not any(diagnostic.severity == "error" for diagnostic in self.diagnostics)
