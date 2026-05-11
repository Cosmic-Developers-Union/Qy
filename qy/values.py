# coding: utf-8

from __future__ import annotations

from collections.abc import Callable
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Final

__all__ = [
    "QY_EMPTY_CHAIN",
    "QY_EMPTY_LIST",
    "QyChain",
    "QyCons",
    "QyEmptyChain",
    "QyEmptyList",
    "iter_qy_chain",
    "iter_qy_list",
    "list_to_qy_chain",
    "list_to_qy_cons",
    "map_qy_chain",
    "map_qy_cons",
    "qy_chain_is_empty",
    "qy_chain_to_tuple",
    "qy_cons_to_tuple",
    "qy_list_is_empty",
]


@dataclass(frozen=True, slots=True, eq=False)
class QyEmptyChain:
    def __iter__(self):
        return iter(())

    def __len__(self) -> int:
        return 0


QY_EMPTY_CHAIN: Final = QyEmptyChain()
QY_EMPTY_LIST: Final = QY_EMPTY_CHAIN
QyEmptyList = QyEmptyChain


@dataclass(frozen=True, slots=True)
class QyChain:
    head: object
    tail: object

    def __iter__(self):
        value: object = self
        while isinstance(value, QyChain):
            yield value.head
            value = value.tail
        if value is not QY_EMPTY_CHAIN:
            raise TypeError("cannot iterate an improper Qy chain")

    def __len__(self) -> int:
        return len(qy_chain_to_tuple(self))


QyCons = QyChain


def qy_chain_is_empty(value: object) -> bool:
    return value is QY_EMPTY_CHAIN


def qy_list_is_empty(value: object) -> bool:
    return qy_chain_is_empty(value)


def list_to_qy_chain(items: Iterable[object], tail: object = QY_EMPTY_CHAIN) -> object:
    result = tail
    for item in reversed(tuple(items)):
        result = QyChain(item, result)
    return result


def list_to_qy_cons(items: Iterable[object], tail: object = QY_EMPTY_LIST) -> object:
    return list_to_qy_chain(items, tail)


def iter_qy_chain(value: object) -> Iterable[object]:
    current = value
    while isinstance(current, QyChain):
        yield current.head
        current = current.tail
    if current is not QY_EMPTY_CHAIN:
        raise TypeError("expected a proper Qy chain")


def iter_qy_list(value: object) -> Iterable[object]:
    return iter_qy_chain(value)


def qy_chain_to_tuple(value: object) -> tuple[object, ...]:
    return tuple(iter_qy_chain(value))


def qy_cons_to_tuple(value: object) -> tuple[object, ...]:
    return qy_chain_to_tuple(value)


def map_qy_chain(value: object, func: Callable[[object], object]) -> object:
    if value is QY_EMPTY_CHAIN:
        return QY_EMPTY_CHAIN
    if isinstance(value, QyChain):
        return QyChain(func(value.head), map_qy_chain(value.tail, func))
    return func(value)


def map_qy_cons(value: object, func: Callable[[object], object]) -> object:
    return map_qy_chain(value, func)
