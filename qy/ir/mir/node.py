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
from qy.frontend.reader import Symbol

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
    "EFFECT_HANDLE_BEGIN",
    "EFFECT_HANDLE_END",
    "EFFECT_RESUME",
    "ENTER_SCOPE",
    "EXIT_SCOPE",
    "FROM_IMPORT",
    "LOAD_CONST",
    "LOAD_HOST",
    "LOAD_ENV",
    "MAKE_FUNCTION",
    "MAKE_MACRO",
    "MOVE",
    "PARALLEL_GATHER",
    "RACE_FIRST",
    "RUNTIME_EVAL",
    "STORE_LOCAL",
]

MIRTerminatorOpcode = Literal[
    "BRANCH",
    "EFFECT_PERFORM",
    "JUMP",
    "RAISE_EFFECT",
    "RETURN",
    "TAIL_CALL",
]


@dataclass(slots=True)
class MIRConstantPool:
    """Constant pool for MIR: stores Python objects referenced by index.

    Each call to ``intern`` appends the value and returns a fresh index.
    Identity semantics are preserved — the same value may appear at multiple
    indices.  Instructions reference constants by integer index instead of
    embedding Python objects directly.
    """

    _values: list[object]

    def __init__(self) -> None:
        self._values = []

    def intern(self, value: object) -> int:
        """Insert *value* into the pool and return its index."""
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
    continuous: bool = False
    """连续算子标记：当 True 时，此指令属于 IR 层不可中断点；
    pass 不得在它所在的连续区间内插入 terminator/scope/effect-region 切换。
    通常由对应 HIR ``CallExpr.continuous`` lowering 而来。"""


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
