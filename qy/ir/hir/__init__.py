# coding: utf-8
"""HIR (High-level IR) — resolved, structured semantic representation.

HIR is emitted by the lowering pass and is the first layer where scoping
is fully resolved and control flow is structural (no jumps/gotos).  All
symbols have been bound, effect/module facts are attached, and the result
is suitable for type analysis, MIR lowering, or interpretation.

Node definitions live in ``node.py``; this module re-exports them for
backward compatibility and provides the ``dump_ir`` helper.
"""

from __future__ import annotations

import pprint

from qy.ir.hir.node import AllExpr
from qy.ir.hir.node import ApplyExpr
from qy.ir.hir.node import AssertExpr
from qy.ir.hir.node import Binding
from qy.ir.hir.node import BindingSource
from qy.ir.hir.node import CacheExpr
from qy.ir.hir.node import CallExpr
from qy.ir.hir.node import CondClause
from qy.ir.hir.node import CondExpr
from qy.ir.hir.node import DefeffectExpr
from qy.ir.hir.node import DefineExpr
from qy.ir.hir.node import DefunExpr
from qy.ir.hir.node import EffectHandler
from qy.ir.hir.node import FromImportExpr
from qy.ir.hir.node import HandleExpr
from qy.ir.hir.node import IRExpr
from qy.ir.hir.node import LambdaExpr
from qy.ir.hir.node import LetBinding
from qy.ir.hir.node import LetExpr
from qy.ir.hir.node import LiteralExpr
from qy.ir.hir.node import MacroExpr
from qy.ir.hir.node import ModuleExpr
from qy.ir.hir.node import ParallelExpr
from qy.ir.hir.node import PerformExpr
from qy.ir.hir.node import PipelineExpr
from qy.ir.hir.node import ProgramIR
from qy.ir.hir.node import QuoteExpr
from qy.ir.hir.node import RaceExpr
from qy.ir.hir.node import ResumeExpr
from qy.ir.hir.node import RuntimeEvalExpr
from qy.ir.hir.node import SymbolRefExpr
from qy.ir.hir.node import UnresolvedSymbolExpr

__all__ = [
    "AllExpr",
    "ApplyExpr",
    "AssertExpr",
    "Binding",
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
    "LambdaExpr",
    "LetBinding",
    "LetExpr",
    "LiteralExpr",
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
    "UnresolvedSymbolExpr",
    "dump_ir",
]


def dump_ir(program: ProgramIR) -> str:
    return pprint.pformat(program, width=100, sort_dicts=False, compact=False)
