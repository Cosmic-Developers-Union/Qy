# coding: utf-8

from __future__ import annotations

import pprint
from dataclasses import dataclass
from dataclasses import field
from typing import Literal

from qy.diagnostics import Diagnostic
from qy.reader import Form
from qy.reader import SourceSpan
from qy.reader import Symbol
from qy.stdlib.imports import ImportSpec
from qy.types import OperatorKind
from qy.types import TypeName

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

BindingSource = Literal["local", "global", "default-literal", "unresolved"]


@dataclass(frozen=True, slots=True)
class Binding:
    symbol: Symbol
    source: BindingSource
    type_name: TypeName
    operator_kind: OperatorKind | None = None
    eager_arguments: bool = True
    value: object | None = field(default=None, compare=False, repr=False)


@dataclass(frozen=True, slots=True)
class ProgramIR:
    body: tuple[IRExpr, ...]
    diagnostics: tuple[Diagnostic, ...] = ()

    @property
    def ok(self) -> bool:
        return not any(diagnostic.severity == "error" for diagnostic in self.diagnostics)


def dump_ir(program: ProgramIR) -> str:
    return pprint.pformat(program, width=100, sort_dicts=False, compact=False)


@dataclass(frozen=True, slots=True)
class LiteralExpr:
    value: object
    type_name: TypeName
    span: SourceSpan | None = None
    source_symbol: Symbol | None = None


@dataclass(frozen=True, slots=True)
class SymbolRefExpr:
    symbol: Symbol
    binding: Binding
    span: SourceSpan | None = None

    @property
    def type_name(self) -> TypeName:
        return self.binding.type_name


@dataclass(frozen=True, slots=True)
class UnresolvedSymbolExpr:
    symbol: Symbol
    span: SourceSpan | None = None
    type_name: TypeName = "unknown"


@dataclass(frozen=True, slots=True)
class QuoteExpr:
    form: Form
    span: SourceSpan | None = None
    type_name: TypeName = "any"


@dataclass(frozen=True, slots=True)
class RuntimeEvalExpr:
    expression: IRExpr
    span: SourceSpan | None = None
    type_name: TypeName = "any"


@dataclass(frozen=True, slots=True)
class CacheExpr:
    expression: IRExpr
    cache_key: object
    span: SourceSpan | None = None
    type_name: TypeName = "any"


@dataclass(frozen=True, slots=True)
class CallExpr:
    operator: IRExpr
    args: tuple[IRExpr, ...]
    span: SourceSpan | None = None
    type_name: TypeName = "any"
    tail_position: bool = False
    raw_args: tuple[object, ...] = field(default=(), compare=False, repr=False)


@dataclass(frozen=True, slots=True)
class LetBinding:
    symbol: Symbol
    value: IRExpr


@dataclass(frozen=True, slots=True)
class LetExpr:
    bindings: tuple[LetBinding, ...]
    body: tuple[IRExpr, ...]
    span: SourceSpan | None = None
    type_name: TypeName = "any"


@dataclass(frozen=True, slots=True)
class LambdaExpr:
    params: tuple[Symbol, ...]
    body: tuple[IRExpr, ...]
    span: SourceSpan | None = None
    type_name: TypeName = "function"


@dataclass(frozen=True, slots=True)
class DefunExpr:
    name: Symbol
    params: tuple[Symbol, ...]
    body: tuple[IRExpr, ...]
    span: SourceSpan | None = None
    type_name: TypeName = "function"


@dataclass(frozen=True, slots=True)
class DefineExpr:
    name: Symbol
    value: IRExpr
    span: SourceSpan | None = None
    type_name: TypeName = "any"


@dataclass(frozen=True, slots=True)
class PipelineExpr:
    body: tuple[IRExpr, ...]
    span: SourceSpan | None = None
    type_name: TypeName = "any"


@dataclass(frozen=True, slots=True)
class ParallelExpr:
    exprs: tuple[IRExpr, ...]
    span: SourceSpan | None = None
    type_name: TypeName = "any"


@dataclass(frozen=True, slots=True)
class AllExpr:
    exprs: tuple[IRExpr, ...]
    span: SourceSpan | None = None
    type_name: TypeName = "any"


@dataclass(frozen=True, slots=True)
class RaceExpr:
    exprs: tuple[IRExpr, ...]
    span: SourceSpan | None = None
    type_name: TypeName = "any"


@dataclass(frozen=True, slots=True)
class ApplyExpr:
    function: IRExpr
    args: IRExpr
    span: SourceSpan | None = None
    type_name: TypeName = "any"


@dataclass(frozen=True, slots=True)
class MacroExpr:
    name: Symbol
    params: tuple[Symbol, ...]
    body: tuple[IRExpr, ...]
    raw_body: tuple[object, ...]
    span: SourceSpan | None = None
    type_name: TypeName = "operator"


@dataclass(frozen=True, slots=True)
class DefeffectExpr:
    name: Symbol
    resumable: bool
    span: SourceSpan | None = None
    type_name: TypeName = "effect"


@dataclass(frozen=True, slots=True)
class CondClause:
    condition: IRExpr
    result: IRExpr


@dataclass(frozen=True, slots=True)
class CondExpr:
    clauses: tuple[CondClause, ...]
    span: SourceSpan | None = None
    type_name: TypeName = "any"


@dataclass(frozen=True, slots=True)
class FromImportExpr:
    module: Symbol
    specs: tuple[ImportSpec, ...]
    span: SourceSpan | None = None
    type_name: TypeName = "none"


@dataclass(frozen=True, slots=True)
class ModuleExpr:
    name: Symbol
    body: tuple[IRExpr, ...]
    export_names: tuple[Symbol, ...] = ()
    span: SourceSpan | None = None
    type_name: TypeName = "any"


@dataclass(frozen=True, slots=True)
class PerformExpr:
    effect: Symbol
    argument: IRExpr
    span: SourceSpan | None = None
    type_name: TypeName = "any"


@dataclass(frozen=True, slots=True)
class EffectHandler:
    effect: Symbol
    arg_name: Symbol
    continuation_name: Symbol
    body: tuple[IRExpr, ...]


@dataclass(frozen=True, slots=True)
class HandleExpr:
    expression: IRExpr
    handlers: tuple[EffectHandler, ...]
    span: SourceSpan | None = None
    type_name: TypeName = "any"


@dataclass(frozen=True, slots=True)
class ResumeExpr:
    continuation: IRExpr
    value: IRExpr
    span: SourceSpan | None = None
    type_name: TypeName = "any"


@dataclass(frozen=True, slots=True)
class AssertExpr:
    condition: IRExpr
    message: IRExpr | None = None
    span: SourceSpan | None = None
    type_name: TypeName = "any"


type IRExpr = (
    AllExpr
    | ApplyExpr
    | AssertExpr
    | CacheExpr
    | CallExpr
    | CondExpr
    | DefeffectExpr
    | DefineExpr
    | DefunExpr
    | FromImportExpr
    | HandleExpr
    | LambdaExpr
    | LetExpr
    | LiteralExpr
    | MacroExpr
    | ModuleExpr
    | ParallelExpr
    | PerformExpr
    | PipelineExpr
    | QuoteExpr
    | RaceExpr
    | ResumeExpr
    | RuntimeEvalExpr
    | SymbolRefExpr
    | UnresolvedSymbolExpr
)
