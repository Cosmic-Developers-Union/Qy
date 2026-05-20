# -*- coding: utf-8 -*-
# Copyright (C) 2025 Cosmic-Developers-Union (CDU), All rights reserved.

"""LIR 节点目标模块。.

目标：
- 放置 LIRProgram、LIRFunction、LIRInstruction、opcode 等节点定义。
- 与 frame/layout、verify、pretty 分离。

禁止：
- 不得放入 VM interpreter 或 bytecode encoder。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from typing import Literal

from qy.diag import Diagnostic
from qy.errors import SourceSpan
from qy.reader import Symbol

if TYPE_CHECKING:
    from qy.ir.lir.frame import LIRContinuationLayout
    from qy.ir.lir.frame import LIRFrameLayout
    from qy.ir.lir.frame import LIRHandlerLayout
    from qy.ir.lir.frame import LIRSymbolSpaceLayout

__all__ = [
    "LIRBindingAddr",
    "LIRBindingSlot",
    "LIRBindingState",
    "LIRDialect",
    "LIRFunction",
    "LIRInstruction",
    "LIRInstructionIndex",
    "LIROpcode",
    "LIRProgram",
    "LIRRegister",
    "LIRSlotIndex",
    "LIRSymbolMeta",
    "LIRSymbolSpaceId",
]

LIRRegister = int
LIRInstructionIndex = int
LIRSymbolSpaceId = int
LIRSlotIndex = int
LIRDialect = Literal["compat", "abstract-machine"]
LIRBindingState = Literal["declared", "pending", "completed", "poisoned"]


@dataclass(frozen=True, slots=True)
class LIRBindingAddr:
    """Stable binding address inside one symbol-space layout."""

    space: LIRSymbolSpaceId
    slot: LIRSlotIndex


@dataclass(frozen=True, slots=True)
class LIRSymbolMeta:
    """Cold metadata for a symbol-space slot."""

    symbol: Symbol
    span: SourceSpan | None = None
    flags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class LIRBindingSlot:
    """One once-complete binding slot in a symbol-space layout."""

    address: LIRBindingAddr
    symbol: Symbol
    state: LIRBindingState = "declared"
    metadata_index: int | None = None


LIROpcode = Literal[
    # -- Value loading --
    "LOAD_HOST",
    "LOAD_NIL",
    "LOAD_T",
    "LOAD_ENV",
    "MOVE",
    # -- Storage --
    "STORE_LOCAL",
    "DEFINE_ONCE",
    # -- Function construction --
    "MAKE_FUNCTION",
    "MAKE_MACRO",
    # -- Scope --
    "ENTER_SCOPE",
    "EXIT_SCOPE",
    # -- Results --
    "APPEND_RESULT",
    # -- Data construction --
    "BUILD_TUPLE",
    # -- Calls --
    "CALL",
    "TAIL_CALL",
    "APPLY",
    # -- Control flow --
    "JUMP",
    "JUMP_IF_FALSE",
    "BRANCH_NIL",
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
    # -- Abstract machine: frame / symbol-space-chain --
    "FRAME_ENTER",
    "FRAME_LEAVE",
    "SS_ENTER",
    "SS_LEAVE",
    "SS_COPY",
    "SS_RESTORE",
    "SS_LOOKUP",
    # -- Abstract machine: binding slot --
    "SLOT_READ",
    "SLOT_COMPLETE",
    "SLOT_PENDING_EFFORT",
    # -- Abstract machine: continuation / handler --
    "CONT_CAPTURE",
    "CONT_COPY",
    "CONT_RESTORE",
    "CONT_INJECT",
    "HANDLER_PUSH",
    "HANDLER_POP",
    "EFFECT_UNWIND",
    "EFFECT_DISPATCH",
]


@dataclass(frozen=True, slots=True)
class LIRInstruction:
    """One LIR instruction with opcode and operands."""

    opcode: LIROpcode
    operands: tuple[object, ...] = ()
    span: SourceSpan | None = None


@dataclass(frozen=True, slots=True)
class LIRFunction:
    """One LIR function with register allocation and instructions."""

    name: Symbol
    params: tuple[Symbol, ...]
    register_count: int
    instructions: tuple[LIRInstruction, ...]
    frame_layout: LIRFrameLayout | None = None
    symbol_spaces: tuple[LIRSymbolSpaceLayout, ...] = ()
    continuations: tuple[LIRContinuationLayout, ...] = ()
    handlers: tuple[LIRHandlerLayout, ...] = ()


@dataclass(frozen=True, slots=True)
class LIRProgram:
    """Complete LIR program with all functions and metadata."""

    functions: tuple[LIRFunction, ...]
    main: int = 0
    diagnostics: tuple[Diagnostic, ...] = ()
    dialect: LIRDialect = "compat"

    @property
    def ok(self) -> bool:
        return not any(diagnostic.severity == "error" for diagnostic in self.diagnostics)
