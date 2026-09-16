# coding: utf-8
"""Core quasiquote desugaring.

``quasiquote`` / ``unquote`` / ``unquote-splicing`` 是核心语法形式
（见 ``LANGUAGE.md`` §Core Built-ins）。把 quasiquote 展开成
``cons`` / ``append`` / ``quote`` 组合属于 core desugaring，其唯一实现放在
这里，供 macro expand 与 HIR lowering 共用：

- 展开是纯 syntax 变换，不执行 runtime evaluation；
- 只处理 ``Symbol`` / ``Chain`` / ``nil``，不产出 Python tuple 或其他宿主值；
- 展开结果保留原 form 的 span。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from qy.core.syntax import Symbol
from qy.core.syntax import car
from qy.core.syntax import cdr
from qy.core.syntax import get_span
from qy.core.syntax import is_chain
from qy.core.syntax import is_nil
from qy.core.syntax import list_to_chain
from qy.core.syntax import nil

if TYPE_CHECKING:
    from qy.source.span import SourceSpan

__all__ = ["expand_quasiquote"]


def expand_quasiquote(form: object, *, depth: int = 0) -> object:
    """把 quasiquote 形式的 syntax datum 展开为构造函数调用。."""
    if is_chain(form) and not is_nil(form):
        operator = car(form)
        rest = cdr(form)
        rest_items = _proper_items(rest)
        argument = rest_items[0] if rest_items is not None and len(rest_items) == 1 else None

        if operator == Symbol("unquote"):
            if argument is None:
                return form
            if depth == 0:
                return argument
            return list_to_chain(
                [Symbol("list"), Symbol("unquote"), expand_quasiquote(argument, depth=depth - 1)],
                span=get_span(form),
            )
        if operator == Symbol("quasiquote"):
            if argument is None:
                return form
            return list_to_chain(
                [
                    Symbol("list"),
                    Symbol("quasiquote"),
                    expand_quasiquote(argument, depth=depth + 1),
                ],
                span=get_span(form),
            )
        return _expand_chain(form, depth=depth)

    return list_to_chain([Symbol("quote"), form], span=get_span(form))


def _proper_items(chain: object) -> list[object] | None:
    if is_nil(chain):
        return []
    if not is_chain(chain):
        return None
    items: list[object] = []
    current: object = chain
    while is_chain(current):
        items.append(car(current))
        current = cdr(current)
    return items if is_nil(current) else None


def _quote(value: object, span: SourceSpan | None) -> object:
    return list_to_chain([Symbol("quote"), value], span=span)


def _expand_chain(form: object, *, depth: int) -> object:
    if is_nil(form):
        return _quote(nil, get_span(form))

    head_form = car(form)
    tail = cdr(form)
    span = get_span(form)

    # ``(unquote-splicing x)`` 作为列表元素：展开为 append
    head_items = _proper_items(head_form)
    if (
        head_items is not None
        and head_items
        and head_items[0] == Symbol("unquote-splicing")
        and depth == 0
    ):
        spliced = head_items[1] if len(head_items) == 2 else head_form
        rest = _expand_chain(tail, depth=depth) if is_chain(tail) else _quote(tail, span)
        return list_to_chain([Symbol("append"), spliced, rest], span=span)

    head = expand_quasiquote(head_form, depth=depth)
    rest = _expand_chain(tail, depth=depth) if is_chain(tail) else _quote(tail, span)
    return list_to_chain([Symbol("cons"), head, rest], span=span)
