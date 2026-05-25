# coding: utf-8
"""Reader Macro 注册表。.

Tagged dispatch 模式：tag → (CstAtom → Form) 的纯转换。
扩展现有 tagged literal 机制 (tag"string" → (tag (quote "string")))。

约束：
- handler 必须是纯函数，无副作用。
- 只对 tagged atom (CstAtom with kind TAGGED_QUOTED/TAGGED_MULTILINE) 触发。
- 未注册的 tag 回退到默认行为。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from dataclasses import field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from qy.frontend.cst import CstAtom
    from qy.frontend.reader import Form

__all__ = [
    "ReaderMacroEntry",
    "ReaderMacroFn",
    "ReaderMacroRegistry",
    "default_registry",
]

type ReaderMacroFn = Callable[["CstAtom"], "Form"]


@dataclass(frozen=True, slots=True)
class ReaderMacroEntry:
    tag: str
    handler: ReaderMacroFn
    doc: str | None = None


@dataclass
class ReaderMacroRegistry:
    """Tag-dispatched reader macro registry."""

    _entries: dict[str, ReaderMacroEntry] = field(default_factory=dict)

    def register(self, tag: str, handler: ReaderMacroFn, *, doc: str | None = None) -> None:
        if tag in self._entries:
            msg = f"reader macro already registered for tag: {tag!r}"
            raise ValueError(msg)
        self._entries[tag] = ReaderMacroEntry(tag, handler, doc)

    def lookup(self, tag: str) -> ReaderMacroEntry | None:
        return self._entries.get(tag)

    def tags(self) -> frozenset[str]:
        return frozenset(self._entries)

    def __contains__(self, tag: str) -> bool:
        return tag in self._entries


def default_registry() -> ReaderMacroRegistry:
    """Built-in reader macros.

    Currently empty — unregistered tags fall through to the default
    tagged literal behavior: tag"lit" → (tag (quote "lit")).
    """
    return ReaderMacroRegistry()
