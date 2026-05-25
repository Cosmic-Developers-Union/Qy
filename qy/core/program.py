# coding: utf-8
"""``CoreProgram`` —— macro 展开后、HIR lowering 前的中间形态。.

``CoreProgram`` 只是一层 marker：内部仍是 ``Form`` 列表（chain/Symbol 的不可变
syntax datum），但已经经过 macro 展开、hygiene 重命名与 reader-macro / surface
sugar 规范化。它是管线中独立的一阶段，使下游 HIR lowering 不再需要关心
macro/surface 细节。

设计要点：
- 不引入新数据形状，仅为类型签名上的边界。
- 携带 ``traces``（macro 展开的 source-map 信息），供后续诊断回溯。
- 不可变。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from qy.frontend.reader import Form
    from qy.macro.trace import MacroExpansionTrace

__all__ = ["CoreProgram"]


@dataclass(frozen=True, slots=True)
class CoreProgram:
    """Macro-expanded syntax datum, not yet HIR-lowered."""

    forms: tuple[Form, ...]
    traces: tuple[MacroExpansionTrace, ...] = ()
