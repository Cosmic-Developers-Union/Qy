# coding: utf-8
# QY_DELETE_AFTER_SEMANTIC_REPLACEMENT: target=qy/core syntax values + qy/sem runtime values

"""Backward-compatibility re-export shim for qy.values.

All canonical definitions have moved:
- ``QyNil``, ``QY_NIL``, ``QY_EMPTY_CHAIN``, ``QY_EMPTY_LIST`` -> :mod:`qy.core.syntax`
- ``QyChain``, ``QyCons`` -> :mod:`qy.core.syntax` (as ``Chain``)
- ``QyT``, ``QY_T`` -> :mod:`qy.sem.core` (as ``TValue``, ``T``)

This module re-exports everything for existing consumers so that migration
can be incremental.  Delete once no file imports from ``qy.values``.
"""

from __future__ import annotations

from collections.abc import Callable
from collections.abc import Iterable
from typing import Final

from qy.core.syntax import Chain
from qy.core.syntax import QyNil
from qy.core.syntax import nil as _nil

__all__ = [
    "QY_EMPTY_CHAIN",
    "QY_EMPTY_LIST",
    "QY_NIL",
    "QY_T",
    "QyChain",
    "QyCons",
    "QyEmptyChain",
    "QyEmptyList",
    "QyNil",
    "QyT",
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

QY_NIL: Final = _nil
QY_EMPTY_CHAIN: Final = QY_NIL
QY_EMPTY_LIST: Final = QY_NIL

QyChain = Chain
QyCons = QyChain
QyEmptyChain = QyNil
QyEmptyList = QyNil

_QY_T_RESOLVED: bool = False


def _resolve_t() -> None:
    global QyT, QY_T, _QY_T_RESOLVED
    if _QY_T_RESOLVED:
        return
    from qy.sem.core import T as _t_singleton
    from qy.sem.core import TValue as _t_type

    QyT = _t_type  # type: ignore[misc]
    QY_T = _t_singleton  # type: ignore[misc]
    _QY_T_RESOLVED = True


def __getattr__(name: str) -> object:
    if name in ("QY_T", "QyT"):
        _resolve_t()
        return globals()[name]
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)


def qy_chain_is_empty(value: object) -> bool:
    return value is QY_EMPTY_CHAIN


def qy_list_is_empty(value: object) -> bool:
    return qy_chain_is_empty(value)


def list_to_qy_chain(items: Iterable[object], tail: object = QY_EMPTY_CHAIN) -> object:
    from qy.core.syntax import cons as _cons

    result = tail
    for item in reversed(tuple(items)):
        result = _cons(item, result)
    return result


def list_to_qy_cons(items: Iterable[object], tail: object = QY_EMPTY_LIST) -> object:
    return list_to_qy_chain(items, tail)


def iter_qy_chain(value: object) -> Iterable[object]:
    current = value
    while isinstance(current, Chain):
        yield current.head
        current = current.tail
    if current is not QY_EMPTY_CHAIN:
        msg = "expected a proper Qy chain"
        raise TypeError(msg)


def iter_qy_list(value: object) -> Iterable[object]:
    return iter_qy_chain(value)


def qy_chain_to_tuple(value: object) -> tuple[object, ...]:
    return tuple(iter_qy_chain(value))


def qy_cons_to_tuple(value: object) -> tuple[object, ...]:
    return qy_chain_to_tuple(value)


def map_qy_chain(value: object, func: Callable[[object], object]) -> object:
    if value is QY_EMPTY_CHAIN:
        return QY_EMPTY_CHAIN
    if isinstance(value, Chain):
        return Chain(func(value.head), map_qy_chain(value.tail, func))
    return func(value)


def map_qy_cons(value: object, func: Callable[[object], object]) -> object:
    return map_qy_chain(value, func)
