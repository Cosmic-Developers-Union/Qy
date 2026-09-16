# coding: utf-8
"""Qy core syntax datum and canonical self-objects.

本模块是 Qy 语法 datum 与规范自对象的唯一真源：

- 语法 datum 只有 ``symbol`` 与不可变 ``chain``；
- ``nil`` / ``T`` / ``none`` 是 Qy 自身对象，三者同处本模块，不由 `qy.sem` 重复定义；
- Python ``None`` 只是宿主互操作值，不等同于 ``none``。
"""

from __future__ import annotations

from collections.abc import Callable
from collections.abc import Iterable
from dataclasses import dataclass
from dataclasses import field
from typing import TYPE_CHECKING
from typing import ClassVar
from typing import TypeGuard
from typing import cast

if TYPE_CHECKING:
    from qy.source.span import SourceSpan

__all__ = [
    "NONE",
    "Chain",
    "Form",
    "NoneValue",
    "QyNil",
    "Symbol",
    "T",
    "TValue",
    "car",
    "cdr",
    "chain_to_list",
    "chain_to_tuple",
    "cons",
    "get_span",
    "is_chain",
    "is_nil",
    "iter_chain",
    "list_to_chain",
    "map_chain",
    "nil",
    "tuple_to_chain",
]


@dataclass(frozen=True, slots=True)
class Symbol:
    """Qy 语法 datum 的原子：一个符号拼写。."""

    name: str
    span: SourceSpan | None = field(default=None, compare=False, repr=False)

    def __str__(self) -> str:
        return self.name


@dataclass(frozen=True, slots=True, eq=False)
class QyNil:
    """The unique empty-chain (nil) type."""

    def __iter__(self):
        return iter(())

    def __len__(self) -> int:
        return 0

    def __bool__(self) -> bool:
        return False


nil = QyNil()


@dataclass(frozen=True, slots=True)
class TValue:
    """Qy 的规范真值对象 ``T``。.

    ``T`` 与 ``nil`` / ``none`` 同属 Qy 自身对象；它不是 Python ``True``。
    """

    type_name: ClassVar[str] = "t"

    def __str__(self) -> str:
        return "T"


@dataclass(frozen=True, slots=True)
class NoneValue:
    """Qy 的 ``none`` 对象。.

    ``none`` 是语言级对象；Python ``None`` 只是实现内部的宿主互操作值，
    标准 profile 暴露的是这里的单例。
    """

    type_name: ClassVar[str] = "none"

    def __str__(self) -> str:
        return "none"


T = TValue()
NONE = NoneValue()


@dataclass(frozen=True, slots=True)
class Chain:
    """Immutable chain (cons cell)."""

    head: object
    tail: object
    span: SourceSpan | None = field(default=None, compare=False, repr=False)

    def __iter__(self):
        current = self
        while is_chain(current):
            yield car(current)
            current = cdr(current)
        if not is_nil(current):
            msg = f"Cannot iterate improper list ending with {current!r}"
            raise ValueError(msg)

    def __len__(self) -> int:
        count = 0
        current = self
        while is_chain(current):
            count += 1
            current = cdr(current)
        if not is_nil(current):
            msg = f"Cannot get length of improper list ending with {current!r}"
            raise ValueError(msg)
        return count


def cons(head: object, tail: object, span: SourceSpan | None = None) -> Chain:
    """构造新的 cons cell。."""
    return Chain(head, tail, span)


type Form = Symbol | Chain | QyNil


def get_span(value: object) -> SourceSpan | None:
    """读取 datum 的 source span；没有 span 时返回 None。."""
    if isinstance(value, Symbol):
        return value.span
    if isinstance(value, Chain):
        return value.span
    return cast("SourceSpan | None", getattr(value, "span", None))


def car(chain: object) -> object:
    """获取 chain 的 head（第一个元素）。."""
    if not isinstance(chain, Chain):
        msg = f"car expects a Chain, got {type(chain).__name__}"
        raise TypeError(msg)
    return chain.head


def cdr(chain: object) -> object:
    """获取 chain 的 tail（剩余部分）。."""
    if not isinstance(chain, Chain):
        msg = f"cdr expects a Chain, got {type(chain).__name__}"
        raise TypeError(msg)
    return chain.tail


def is_nil(obj: object) -> bool:
    """判断对象是否为 nil（空链）。."""
    return obj is nil or isinstance(obj, QyNil)


def is_chain(obj: object) -> TypeGuard[Chain]:
    """判断对象是否为 Chain。."""
    return isinstance(obj, Chain)


def chain_to_list(chain: object) -> list[object]:
    """将 proper chain 转换为 Python list。."""
    if is_nil(chain):
        return []

    result = []
    current = chain
    while is_chain(current):
        result.append(car(current))
        current = cdr(current)

    if not is_nil(current):
        msg = f"Cannot convert improper list to Python list, tail is {current!r}"
        raise ValueError(msg)

    return result


def list_to_chain(
    items: Iterable[object], tail: Form | None = None, span: SourceSpan | None = None
) -> Form:
    """从 Python iterable 构造 chain。."""
    if tail is None:
        tail = nil

    result = tail
    items_list = list(items)

    for i, item in enumerate(reversed(items_list)):
        item_span = span if i == len(items_list) - 1 else None
        result = cons(item, result, item_span)

    return result


def tuple_to_chain(t: tuple[object, ...], span: SourceSpan | None = None) -> Form:
    """将 Python tuple 转换为 chain。."""
    return list_to_chain(t, span=span)


def chain_to_tuple(chain: object) -> tuple[object, ...]:
    """将 proper chain 转换为 Python tuple。."""
    return tuple(chain_to_list(chain))


def iter_chain(chain: object) -> Iterable[object]:
    """惰性迭代 proper chain 的元素。."""
    current = chain
    while isinstance(current, Chain):
        yield current.head
        current = current.tail
    if not is_nil(current):
        msg = f"Cannot iterate improper list ending with {current!r}"
        raise TypeError(msg)


def map_chain(chain: object, func: Callable[[object], object]) -> object:
    """对 chain 每个元素应用 func，返回新 chain。."""
    if is_nil(chain):
        return nil
    if isinstance(chain, Chain):
        return Chain(func(chain.head), map_chain(chain.tail, func))
    return func(chain)
