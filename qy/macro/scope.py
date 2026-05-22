# -*- coding: utf-8 -*-
# Copyright (C) 2025 Cosmic-Developers-Union (CDU), All rights reserved.

"""Macro scope management."""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field

from qy.frontend.reader import Symbol
from qy.macro import MacroDefinition

__all__ = ["MacroScope"]


@dataclass(slots=True)
class MacroScope:
    parent: MacroScope | None = None
    publish_definitions: bool = False
    bindings: dict[Symbol, MacroDefinition] = field(default_factory=dict)

    def child(self, *, publish_definitions: bool = False) -> MacroScope:
        return MacroScope(self, publish_definitions)

    def define(self, name: Symbol, value: MacroDefinition) -> None:
        self.bindings[name] = value

    def lookup(self, name: Symbol) -> MacroDefinition | None:
        if name in self.bindings:
            return self.bindings[name]
        if self.parent is not None:
            return self.parent.lookup(name)
        return None
