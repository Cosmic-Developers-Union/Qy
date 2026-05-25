# coding: utf-8
"""Concrete Syntax Tree (CST) 数据结构。.

CST 是源码的保真表示：拼接所有节点的 text 字段可还原原始源码。
它保留 whitespace、comment、delimiter 等所有 token 信息。

用途：
- formatter (trivia-aware formatting)
- LSP (精确 span, hover, goto-definition)
- reader macro dispatch (tagged atom → Form)

设计：
- Frozen dataclasses, immutable.
- Leading trivia 约定：trivia 附属于其后的第一个 form。
- CstNode = CstAtom | CstList (形式节点)
- Comments 作为 trivia 的一部分保留在 leading_trivia 字段中。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

from qy.errors import SourceSpan

__all__ = [
    "AtomKind",
    "CstAtom",
    "CstList",
    "CstNode",
    "CstProgram",
    "collect_text",
    "iter_forms",
]


class AtomKind(Enum):
    BARE = "bare"
    QUOTED = "quoted"
    RAW_QUOTED = "raw_quoted"
    TAGGED_QUOTED = "tagged_quoted"
    MULTILINE = "multiline"
    RAW_MULTILINE = "raw_multiline"
    TAGGED_MULTILINE = "tagged_multiline"


@dataclass(frozen=True, slots=True)
class CstAtom:
    kind: AtomKind
    text: str
    span: SourceSpan
    leading_trivia: str = ""


@dataclass(frozen=True, slots=True)
class CstList:
    """Parenthesized list.

    Structure for roundtrip reconstruction:
      leading_trivia + "(" + children[0..n] + [dot_trivia + "." + tail] + close_trivia + ")"

    For dotted pair (a . b):
      children = [CstAtom("a")] (forms before dot)
      dot_trivia = " "  (trivia before dot)
      tail = CstAtom("b") (form after dot, with its own leading_trivia)
      close_trivia = "" (trivia before close paren)
    """

    children: tuple[CstNode, ...]
    span: SourceSpan
    leading_trivia: str = ""
    dot_trivia: str = ""
    tail: CstNode | None = None
    close_trivia: str = ""

    @property
    def is_dotted(self) -> bool:
        return self.tail is not None


type CstNode = CstAtom | CstList


@dataclass(frozen=True, slots=True)
class CstProgram:
    children: tuple[CstNode, ...]
    trailing_trivia: str
    span: SourceSpan


def collect_text(program: CstProgram) -> str:
    """Roundtrip: 拼接 CstProgram 所有 text → 原始源码。."""
    parts: list[str] = []
    for node in program.children:
        _collect_node(node, parts)
    parts.append(program.trailing_trivia)
    return "".join(parts)


def _collect_node(node: CstNode, parts: list[str]) -> None:
    match node:
        case CstAtom(leading_trivia=lt, text=text):
            parts.append(lt)
            parts.append(text)
        case CstList(
            leading_trivia=lt,
            children=children,
            dot_trivia=dt,
            tail=tail,
            close_trivia=ct,
        ):
            parts.append(lt)
            parts.append("(")
            for child in children:
                _collect_node(child, parts)
            if tail is not None:
                parts.append(dt)
                parts.append(".")
                _collect_node(tail, parts)
            parts.append(ct)
            parts.append(")")


def iter_forms(program: CstProgram) -> Iterator[CstAtom | CstList]:
    """Iterate only top-level form nodes."""
    yield from program.children
