# coding: utf-8
"""Build pipeline artifact wrappers and kind names."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from qy.frontend.form import Form

SOURCE = "source"
CST = "cst"
RAW_FORMS = "raw-forms"
SURFACE_FORMS = "surface-forms"
CORE_AST = "core-ast"
HIR = "hir"
MIR = "mir"
LIR = "lir"
BYTECODE = "bytecode"

ArtifactKind = Literal[
    "source",
    "cst",
    "raw-forms",
    "surface-forms",
    "core-ast",
    "hir",
    "mir",
    "lir",
    "bytecode",
]


@dataclass(frozen=True, slots=True)
class SourceProgram:
    source: str
    source_name: str | None = None


@dataclass(frozen=True, slots=True)
class RawFormProgram:
    forms: tuple[Form, ...]


@dataclass(frozen=True, slots=True)
class SurfaceProgram:
    forms: tuple[Form, ...]


__all__ = [
    "BYTECODE",
    "CORE_AST",
    "CST",
    "HIR",
    "LIR",
    "MIR",
    "RAW_FORMS",
    "SOURCE",
    "SURFACE_FORMS",
    "ArtifactKind",
    "RawFormProgram",
    "SourceProgram",
    "SurfaceProgram",
]
