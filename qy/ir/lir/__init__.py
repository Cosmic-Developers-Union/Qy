# coding: utf-8
"""LIR (Low-level IR): Qy abstract-machine IR.

LIR is the first layer where Qy's runtime machinery must be explicit.  It is
VM-facing, but it is not bytecode and it is not a textual copy of bytecode.
The final target model is an abstract machine with virtual-stack frames,
continuation frames, handler frames, symbol-space-chain transitions, binding
slot operations, and explicit lookup operations.

The current compiler still emits ``compat`` LIR for some legacy bytecode
instructions while the abstract-machine vocabulary is being introduced.  New
low-level work should model runtime mechanisms here instead of hiding them in
the bytecode compiler or register VM.

NOTE: ``LIRProgram``, ``LIRFunction``, ``LIRInstruction`` are canonically
defined in this package.  The legacy ``qy.lir`` path was removed in favor
of this package as the single source of truth.
"""

from __future__ import annotations

from qy.ir.lir.frame import LIRContinuationLayout
from qy.ir.lir.frame import LIRFrameKind
from qy.ir.lir.frame import LIRFrameLayout
from qy.ir.lir.frame import LIRHandlerLayout
from qy.ir.lir.frame import LIRSymbolSpaceLayout
from qy.ir.lir.node import LIRBindingAddr
from qy.ir.lir.node import LIRBindingSlot
from qy.ir.lir.node import LIRBindingState
from qy.ir.lir.node import LIRDialect
from qy.ir.lir.node import LIRFunction
from qy.ir.lir.node import LIRInstruction
from qy.ir.lir.node import LIRInstructionIndex
from qy.ir.lir.node import LIROpcode
from qy.ir.lir.node import LIRProgram
from qy.ir.lir.node import LIRRegister
from qy.ir.lir.node import LIRSlotIndex
from qy.ir.lir.node import LIRSymbolMeta
from qy.ir.lir.node import LIRSymbolSpaceId
from qy.ir.lir.pretty import dump_lir
from qy.ir.lir.verify import verify_lir

__all__ = [
    "LIRBindingAddr",
    "LIRBindingSlot",
    "LIRBindingState",
    "LIRContinuationLayout",
    "LIRDialect",
    "LIRFrameKind",
    "LIRFrameLayout",
    "LIRFunction",
    "LIRHandlerLayout",
    "LIRInstruction",
    "LIRInstructionIndex",
    "LIROpcode",
    "LIRProgram",
    "LIRRegister",
    "LIRSlotIndex",
    "LIRSymbolMeta",
    "LIRSymbolSpaceId",
    "LIRSymbolSpaceLayout",
    "dump_lir",
    "verify_lir",
]
