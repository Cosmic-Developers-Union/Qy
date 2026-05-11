# coding: utf-8

from __future__ import annotations

from collections.abc import Callable
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Final

__all__ = [
    "QY_EMPTY_LIST",
    "QyCons",
    "QyEmptyList",
    "iter_qy_list",
    "list_to_qy_cons",
    "map_qy_cons",
    "qy_cons_to_tuple",
    "qy_list_is_empty",
]


@dataclass(frozen=True, slots=True, eq=False)
class QyEmptyList:
    def __iter__(self):
        return iter(())

    def __len__(self) -> int:
        return 0


QY_EMPTY_LIST: Final = QyEmptyList()


@dataclass(frozen=True, slots=True)
class QyCons:
    head: object
    tail: object

    def __iter__(self):
        value: object = self
        while isinstance(value, QyCons):
            yield value.head
            value = value.tail
        if value is not QY_EMPTY_LIST:
            raise TypeError("cannot iterate an improper Qy cons list")

    def __len__(self) -> int:
        return len(qy_cons_to_tuple(self))


def qy_list_is_empty(value: object) -> bool:
    return value is QY_EMPTY_LIST


def list_to_qy_cons(items: Iterable[object], tail: object = QY_EMPTY_LIST) -> object:
    result = tail
    for item in reversed(tuple(items)):
        result = QyCons(item, result)
    return result


def iter_qy_list(value: object) -> Iterable[object]:
    current = value
    while isinstance(current, QyCons):
        yield current.head
        current = current.tail
    if current is not QY_EMPTY_LIST:
        raise TypeError("expected a proper Qy cons list")


def qy_cons_to_tuple(value: object) -> tuple[object, ...]:
    return tuple(iter_qy_list(value))


def map_qy_cons(value: object, func: Callable[[object], object]) -> object:
    if value is QY_EMPTY_LIST:
        return QY_EMPTY_LIST
    if isinstance(value, QyCons):
        return QyCons(func(value.head), map_qy_cons(value.tail, func))
    return func(value)
