# coding: utf-8
"""前端 Form 基础类型。."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from dataclasses import field
from typing import cast

from qy.core.syntax import Chain
from qy.core.syntax import list_to_chain
from qy.source.span import SourceSpan

__all__ = [
    "DottedTuple",
    "Form",
    "SpannedTuple",
    "Symbol",
    "TupleForm",
    "chain_to_spanned_tuple",
    "get_span",
    "spanned_tuple_to_chain",
]


@dataclass(frozen=True, slots=True)
class Symbol:
    name: str
    span: SourceSpan | None = field(default=None, compare=False, repr=False)

    def __str__(self) -> str:
        return self.name


class SpannedTuple(tuple):
    span: SourceSpan | None

    def __new__(cls, items: Iterable[object] = (), span: SourceSpan | None = None) -> SpannedTuple:
        value = super().__new__(cls, items)
        value.span = span
        return value


class DottedTuple(tuple):
    tail: object
    span: SourceSpan | None

    def __new__(
        cls,
        items: Iterable[object] = (),
        tail: object = None,
        span: SourceSpan | None = None,
    ) -> DottedTuple:
        value = super().__new__(cls, items)
        value.tail = tail
        value.span = span
        return value


# 目标是 Symbol | Chain；迁移期间保留 tuple 类型以支持兼容层。
type Form = Symbol | Chain | SpannedTuple | DottedTuple | tuple["Form", ...]
type TupleAtom = Symbol | str | int | float | bool | bytes | None
type TupleForm = TupleAtom | tuple["TupleForm", ...]


def get_span(value: object) -> SourceSpan | None:
    if isinstance(value, Symbol):
        return value.span
    if isinstance(value, Chain):
        return value.span
    return cast("SourceSpan | None", getattr(value, "span", None))


def chain_to_spanned_tuple(chain: Chain) -> tuple:
    items = list(chain)
    return SpannedTuple(items, get_span(chain))


def spanned_tuple_to_chain(t: tuple) -> object:
    return list_to_chain(list(t), span=get_span(t))
