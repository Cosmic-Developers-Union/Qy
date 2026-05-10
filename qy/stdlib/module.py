# coding: utf-8

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from qy.reader import Symbol


@dataclass(frozen=True, slots=True)
class StandardModule:
    name: str
    exports: Mapping[Symbol, object]

    def resolve(self, name: Symbol) -> object:
        try:
            return self.exports[name]
        except KeyError as e:
            raise KeyError(f"module {self.name!r} has no export {name.name!r}") from e
