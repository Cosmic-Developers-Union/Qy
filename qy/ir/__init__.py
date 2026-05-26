# coding: utf-8
"""IR models — HIR, MIR, and LIR.

Public API (re-exported from qy/__init__.py):
    from qy.ir import ProgramIR, Binding, CallExpr, ...
    from qy.ir import LIRProgram, LIRFunction, LIRInstruction, ...
    from qy.ir import MIRProgram, MIRFunction, MIRInstruction, MIRTerminator, ...
"""

from __future__ import annotations

from qy.ir.hir import AllExpr
from qy.ir.hir import ApplyExpr
from qy.ir.hir import AssertExpr
from qy.ir.hir import Binding
from qy.ir.hir import BindingRef
from qy.ir.hir import BindingSource
from qy.ir.hir import CacheExpr
from qy.ir.hir import CallExpr
from qy.ir.hir import CondClause
from qy.ir.hir import CondExpr
from qy.ir.hir import DefeffectExpr
from qy.ir.hir import DefineExpr
from qy.ir.hir import DefunExpr
from qy.ir.hir import EffectHandler
from qy.ir.hir import FromImportExpr
from qy.ir.hir import HandleExpr
from qy.ir.hir import IRExpr
from qy.ir.hir import LambdaExpr
from qy.ir.hir import LetBinding
from qy.ir.hir import LetExpr
from qy.ir.hir import LiteralExpr
from qy.ir.hir import MacroExpr
from qy.ir.hir import ModuleExpr
from qy.ir.hir import ParallelExpr
from qy.ir.hir import PerformExpr
from qy.ir.hir import PipelineExpr
from qy.ir.hir import ProgramIR
from qy.ir.hir import QuoteExpr
from qy.ir.hir import RaceExpr
from qy.ir.hir import ResumeExpr
from qy.ir.hir import RuntimeEvalExpr
from qy.ir.hir import SymbolRefExpr
from qy.ir.hir import SymbolSpace
from qy.ir.hir import UnresolvedSymbolExpr
from qy.ir.hir import dump_ir
from qy.ir.lir import LIRBindingAddr
from qy.ir.lir import LIRBindingSlot
from qy.ir.lir import LIRBindingState
from qy.ir.lir import LIRContinuationLayout
from qy.ir.lir import LIRFrameKind
from qy.ir.lir import LIRFrameLayout
from qy.ir.lir import LIRFunction
from qy.ir.lir import LIRHandlerLayout
from qy.ir.lir import LIRInstruction
from qy.ir.lir import LIRInstructionIndex
from qy.ir.lir import LIROpcode
from qy.ir.lir import LIRProgram
from qy.ir.lir import LIRRegister
from qy.ir.lir import LIRSlotIndex
from qy.ir.lir import LIRSymbolMeta
from qy.ir.lir import LIRSymbolSpaceId
from qy.ir.lir import LIRSymbolSpaceLayout
from qy.ir.lir import dump_lir
from qy.ir.lir import verify_lir
from qy.ir.mir import MIRBlock
from qy.ir.mir import MIRBlockId
from qy.ir.mir import MIRConstantPool
from qy.ir.mir import MIRFunction
from qy.ir.mir import MIRInstruction
from qy.ir.mir import MIROpcode
from qy.ir.mir import MIRProgram
from qy.ir.mir import MIRRegister
from qy.ir.mir import MIRTerminator
from qy.ir.mir import MIRTerminatorOpcode
from qy.ir.mir import dump_mir
from qy.ir.mir import verify_mir

__all__ = [
    # HIR
    "AllExpr",
    "ApplyExpr",
    "AssertExpr",
    "Binding",
    "BindingRef",
    "BindingSource",
    "CacheExpr",
    "CallExpr",
    "CondClause",
    "CondExpr",
    "DefeffectExpr",
    "DefineExpr",
    "DefunExpr",
    "EffectHandler",
    "FromImportExpr",
    "HandleExpr",
    "IRExpr",
    "LIRBindingAddr",
    "LIRBindingSlot",
    "LIRBindingState",
    "LIRContinuationLayout",
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
    "LambdaExpr",
    "LetBinding",
    "LetExpr",
    "LiteralExpr",
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
    "MacroExpr",
    "ModuleExpr",
    "ParallelExpr",
    "PerformExpr",
    "PipelineExpr",
    "ProgramIR",
    "QuoteExpr",
    "RaceExpr",
    "ResumeExpr",
    "RuntimeEvalExpr",
    "SymbolRefExpr",
    "SymbolSpace",
    "UnresolvedSymbolExpr",
    "dump_ir",
    # LIR
    "dump_lir",
    # MIR
    "dump_mir",
    "verify_lir",
    "verify_mir",
]
