# coding: utf-8

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from dataclasses import field

from qy.frontend.reader import Symbol


@dataclass(frozen=True, slots=True)
class StandardModule:
    name: str
    exports: Mapping[Symbol, object]
    macro_exports: Mapping[Symbol, object] = field(default_factory=dict)

    def resolve(self, name: Symbol) -> object:
        try:
            return self.exports[name]
        except KeyError as e:
            raise KeyError(f"module {self.name!r} has no export {name.name!r}") from e

    def resolve_macro(self, name: Symbol) -> object:
        try:
            return self.macro_exports[name]
        except KeyError as e:
            raise KeyError(f"module {self.name!r} has no macro export {name.name!r}") from e
