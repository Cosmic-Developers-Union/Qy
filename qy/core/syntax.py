# coding: utf-8
"""Qy 核心语法数据结构。.

提供统一的 immutable Chain 表示，同时服务 syntax datum 和 runtime value。

核心类型：
- Chain: immutable cons cell，带可选 span 追踪
- nil: 空链表示（使用 QyNil 单例）

设计原则：
- Chain 是 frozen dataclass，完全不可变
- span 不参与相等性比较（compare=False）
- 支持 proper list 和 improper list
- 提供 cons/car/cdr 等 Lisp 风格操作
- 提供与 Python list/tuple 的转换函数
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from dataclasses import field
from typing import TYPE_CHECKING

from qy.values import QY_NIL
from qy.values import QyNil

if TYPE_CHECKING:
    from qy.errors import SourceSpan

__all__ = [
    "Chain",
    "car",
    "cdr",
    "chain_to_list",
    "chain_to_tuple",
    "cons",
    "is_chain",
    "is_nil",
    "list_to_chain",
    "nil",
    "tuple_to_chain",
]


# 使用现有的 QyNil 单例作为空链表示
nil = QY_NIL


@dataclass(frozen=True, slots=True)
class Chain:
    """Immutable chain (cons cell)。.

    同时用于 syntax datum 和 runtime value。

    结构：
    - head: car，链表头元素
    - tail: cdr，链表尾部（可以是另一个 Chain、nil 或任意值）
    - span: 可选的源码位置信息（不参与相等性比较）

    示例：
        # Proper list: (1 2 3)
        list_to_chain([1, 2, 3])
        # => Chain(1, Chain(2, Chain(3, nil)))

        # Improper list: (1 . 2)
        cons(1, 2)
        # => Chain(1, 2)

        # 带 span 的 chain
        Chain(Symbol("x"), nil, span=some_span)
    """

    head: object  # car
    tail: object  # cdr，可以是另一个 Chain 或 nil
    span: SourceSpan | None = field(default=None, compare=False, repr=False)

    def __iter__(self):
        """迭代 proper list 的元素。.

        对于 improper list 会抛出 ValueError。
        """
        current = self
        while is_chain(current):
            yield car(current)
            current = cdr(current)
        if not is_nil(current):
            raise ValueError(f"Cannot iterate improper list ending with {current!r}")

    def __len__(self) -> int:
        """返回 proper list 的长度。.

        对于 improper list 会抛出 ValueError。
        """
        count = 0
        current = self
        while is_chain(current):
            count += 1
            current = cdr(current)
        if not is_nil(current):
            raise ValueError(f"Cannot get length of improper list ending with {current!r}")
        return count


# ============================================================================
# 基础操作（Lisp 风格）
# ============================================================================


def cons(head: object, tail: object, span: SourceSpan | None = None) -> Chain:
    """构造新的 cons cell。.

    Args:
        head: car，链表头元素
        tail: cdr，链表尾部（通常是另一个 Chain 或 nil）
        span: 可选的源码位置信息

    Returns:
        新的 Chain 实例

    示例：
        cons(1, nil)  # => (1)
        cons(1, cons(2, nil))  # => (1 2)
        cons(1, 2)  # => (1 . 2) improper list
    """
    return Chain(head, tail, span)


def car(chain: object) -> object:
    """获取 chain 的 head（第一个元素）。."""
    if not isinstance(chain, Chain):
        raise TypeError(f"car expects a Chain, got {type(chain).__name__}")
    return chain.head


def cdr(chain: object) -> object:
    """获取 chain 的 tail（剩余部分）。."""
    if not isinstance(chain, Chain):
        raise TypeError(f"cdr expects a Chain, got {type(chain).__name__}")
    return chain.tail


def is_nil(obj: object) -> bool:
    """判断对象是否为 nil（空链）。.

    Args:
        obj: 要检查的对象

    Returns:
        如果是 nil 返回 True，否则返回 False
    """
    return obj is nil or isinstance(obj, QyNil)


def is_chain(obj: object) -> bool:
    """判断对象是否为 Chain。.

    Args:
        obj: 要检查的对象

    Returns:
        如果是 Chain 返回 True，否则返回 False
    """
    return isinstance(obj, Chain)


# ============================================================================
# 转换函数
# ============================================================================


def chain_to_list(chain: object) -> list[object]:
    """将 proper chain 转换为 Python list。.

    Args:
        chain: Chain 或 nil

    Returns:
        包含所有元素的 Python list

    Raises:
        ValueError: 如果是 improper list

    示例：
        chain_to_list(list_to_chain([1, 2, 3]))  # => [1, 2, 3]
        chain_to_list(nil)  # => []
    """
    if is_nil(chain):
        return []

    result = []
    current = chain
    while is_chain(current):
        result.append(car(current))
        current = cdr(current)

    if not is_nil(current):
        raise ValueError(f"Cannot convert improper list to Python list, tail is {current!r}")

    return result


def list_to_chain(
    items: Iterable[object], tail: object = None, span: SourceSpan | None = None
) -> object:
    """从 Python iterable 构造 chain。.

    Args:
        items: 要转换的元素序列
        tail: 链表尾部（默认为 nil，可以指定其他值构造 improper list）
        span: 可选的源码位置信息（应用于最外层 Chain）

    Returns:
        构造的 Chain 或 nil（如果 items 为空且 tail 为 nil）

    示例：
        list_to_chain([1, 2, 3])  # => (1 2 3)
        list_to_chain([1, 2], tail=3)  # => (1 2 . 3)
        list_to_chain([])  # => nil
    """
    if tail is None:
        tail = nil

    result = tail
    items_list = list(items)

    # 从后向前构造，最后一个 cons 带 span
    for i, item in enumerate(reversed(items_list)):
        item_span = span if i == len(items_list) - 1 else None
        result = cons(item, result, item_span)

    return result


def tuple_to_chain(t: tuple[object, ...], span: SourceSpan | None = None) -> object:
    """将 Python tuple 转换为 chain（迁移期兼容函数）。.

    Args:
        t: Python tuple
        span: 可选的源码位置信息

    Returns:
        构造的 Chain 或 nil

    示例：
        tuple_to_chain((1, 2, 3))  # => (1 2 3)
        tuple_to_chain(())  # => nil
    """
    return list_to_chain(t, span=span)


def chain_to_tuple(chain: object) -> tuple[object, ...]:
    """将 proper chain 转换为 Python tuple（迁移期兼容函数）。.

    Args:
        chain: Chain 或 nil

    Returns:
        包含所有元素的 Python tuple

    Raises:
        ValueError: 如果是 improper list

    示例:
        chain_to_tuple(list_to_chain([1, 2, 3]))  # => (1, 2, 3)
        chain_to_tuple(nil)  # => ()
    """
    return tuple(chain_to_list(chain))
