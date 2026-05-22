# -*- coding: utf-8 -*-
# Copyright (C) 2025 Cosmic-Developers-Union (CDU), All rights reserved.

"""LIR frame/layout 目标模块。.

目标：
- 建模 virtual stack frame、continuation frame、handler frame、task frame。
- 建模 symbol-space-chain transition、binding slot layout、handler table layout。

禁止：
- 不得把 frame 语义留给 VM 临时 Python 对象隐式承担。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from typing import Literal

if TYPE_CHECKING:
    from qy.frontend.reader import Symbol
    from qy.ir.lir.node import LIRBindingSlot
    from qy.ir.lir.node import LIRInstructionIndex
    from qy.ir.lir.node import LIRRegister
    from qy.ir.lir.node import LIRSymbolMeta
    from qy.ir.lir.node import LIRSymbolSpaceId

__all__ = [
    "LIRContinuationLayout",
    "LIRFrameKind",
    "LIRFrameLayout",
    "LIRHandlerLayout",
    "LIRSymbolSpaceLayout",
]

LIRFrameKind = Literal["function", "continuation", "handler", "task"]


@dataclass(frozen=True, slots=True)
class LIRSymbolSpaceLayout:
    """Low-level symbol-space layout visible to LIR and later backends."""

    id: LIRSymbolSpaceId
    name: str
    parent: LIRSymbolSpaceId | None = None
    slots: tuple[LIRBindingSlot, ...] = ()
    metadata: tuple[LIRSymbolMeta, ...] = ()


@dataclass(frozen=True, slots=True)
class LIRFrameLayout:
    """Frame layout for one Qy abstract-machine frame."""

    kind: LIRFrameKind
    name: str
    register_count: int
    local_slot_count: int = 0
    ss_chain: tuple[LIRSymbolSpaceId, ...] = ()
    saved_registers: tuple[LIRRegister, ...] = ()


@dataclass(frozen=True, slots=True)
class LIRContinuationLayout:
    """Delimited continuation layout captured by effect lowering."""

    id: int
    resume_target: LIRInstructionIndex | None = None
    saved_registers: tuple[LIRRegister, ...] = ()
    saved_spaces: tuple[LIRSymbolSpaceId, ...] = ()
    multi_shot: bool = True


@dataclass(frozen=True, slots=True)
class LIRHandlerLayout:
    """Effect handler marker layout on the virtual stack."""

    id: int
    effects: tuple[Symbol, ...] = ()
    handler_target: LIRInstructionIndex | None = None
    parent_handler: int | None = None
    ss_chain: tuple[LIRSymbolSpaceId, ...] = ()
