# -*- coding: utf-8 -*-
# Copyright (C) 2025 Cosmic-Developers-Union (CDU), All rights reserved.

"""Macro expansion trace and source map."""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field

from qy.macro.hygiene import MacroRename
from qy.reader import SourceSpan
from qy.reader import Symbol

__all__ = ["MacroExpansionTrace", "MacroSourceMapEntry"]


@dataclass(frozen=True, slots=True)
class MacroSourceMapEntry:
    macro: Symbol
    original_span: SourceSpan | None
    expanded_span: SourceSpan | None
    depth: int
    generated_symbols: tuple[Symbol, ...] = ()
    renames: tuple[MacroRename, ...] = ()


@dataclass(frozen=True, slots=True)
class MacroExpansionTrace:
    macro: Symbol
    input_span: SourceSpan | None
    output_span: SourceSpan | None
    depth: int
    input_form: object = field(compare=False, repr=False)
    output_form: object = field(compare=False, repr=False)
    generated_symbols: tuple[Symbol, ...] = ()
    renames: tuple[MacroRename, ...] = ()

    def source_map_entry(self) -> MacroSourceMapEntry:
        return MacroSourceMapEntry(
            self.macro,
            self.input_span,
            self.output_span,
            self.depth,
            self.generated_symbols,
            self.renames,
        )
