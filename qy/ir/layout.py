# coding: utf-8
"""Shared IR-level symbol-space layout facts.

HIR 层的 ``resolve.spaces`` 产出 binding id/slot 事实；MIR / LIR 需要在不
互相 import 对方 IR 包的前提下携带这份事实。因此 layout 类型放在这个
中性模块里，由各 IR 层引用。

- :class:`BindingSlot`：一个 once-complete binding 的 slot（symbol + index）。
- :class:`SymbolSpaceLayout`：一个 lexical symbol-space 的稳定 id / parent /
  slot 列表。

禁止：
- 不得包含执行语义或 VM 实现细节。
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field

from qy.core.syntax import Symbol

__all__ = ["BindingSlot", "SymbolSpaceLayout"]


@dataclass(frozen=True, slots=True)
class BindingSlot:
    """One once-complete binding slot in a symbol-space layout."""

    symbol: Symbol
    index: int
    source: str = "define"


@dataclass(frozen=True, slots=True)
class SymbolSpaceLayout:
    """Stable id / parent / slots for one lexical symbol-space."""

    id: int
    name: str
    parent: int | None
    slots: tuple[BindingSlot, ...] = field(default_factory=tuple)
