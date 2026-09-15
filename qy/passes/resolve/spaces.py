# coding: utf-8
"""resolve.spaces pass。.

目标：
- 为 HIR 中 lowering 期创建的 lexical symbol-space 分配稳定 id；
- 把每个 space 内的 symbol 绑定固化为 slot index；
- 产出可序列化的 :class:`HIRSymbolSpaceLayout` 列表，挂到 ``ProgramIR``。

当前：
- 这是 HIR 层的 layout 事实来源。``hir.lower`` 在定义绑定时已经填充
  ``SymbolSpace.bindings``（symbol -> slot index）；本 pass 只负责把
  "哪些 space 属于本程序、id 是多少、parent 是谁" 显式化，不重新推导作用域。
- profile 预装空间（只含 ``builtin`` 绑定）会被过滤掉，不属于程序的 lexical
  layout。
- 仍待推进：MIR 携带 binding id/slot（当前 MIR 的 ``DEFINE_ONCE`` /
  ``LOAD_ENV`` 只带 symbol 名），LIR 才能真正从 HIR 事实而不是指令流重建
  ``symbol_spaces``；pending binding / meta-space 尚未建模。

禁止：
- 不执行 runtime evaluation，不改变 ``ProgramIR.body``。
"""

from __future__ import annotations

from dataclasses import fields
from dataclasses import is_dataclass
from typing import cast

from qy.ir.hir import Binding
from qy.ir.hir import BindingSource
from qy.ir.hir import DefineExpr
from qy.ir.hir import DefunExpr
from qy.ir.hir import HIRBindingSlot
from qy.ir.hir import HIRSymbolSpaceLayout
from qy.ir.hir import ProgramIR
from qy.ir.hir import SymbolSpace
from qy.passes.pass_base import Pass
from qy.passes.pass_base import PassContext
from qy.passes.pass_base import PassResult

__all__ = ["ResolveSpacesPass", "collect_symbol_spaces"]


def _iter_nodes(node: object):
    """Yield *node* and every dataclass reachable through its fields.

    ``SymbolSpace`` 是遍历边界：只 yield 它本身，不进入其 parent / bindings，
    以免爬进整个 profile 链。
    """
    if isinstance(node, SymbolSpace):
        yield node
        return
    if is_dataclass(node) and not isinstance(node, type):
        yield node
        for field_info in fields(node):
            yield from _iter_nodes(getattr(node, field_info.name))
        return
    if isinstance(node, (tuple, list)):
        for item in node:
            yield from _iter_nodes(item)


def collect_symbol_spaces(program: ProgramIR) -> tuple[HIRSymbolSpaceLayout, ...]:
    """Build the lexical symbol-space layout for *program*."""
    spaces: dict[int, SymbolSpace] = {}
    sources: dict[tuple[int, str], BindingSource] = {}

    def remember(space: SymbolSpace | None, symbol_name: str | None, source: BindingSource) -> None:
        if space is None:
            return
        key = id(space)
        spaces.setdefault(key, space)
        if symbol_name is not None:
            sources.setdefault((key, symbol_name), source)

    for node in _iter_nodes(program.body):
        if isinstance(node, Binding):
            # profile / builtin bindings are not part of the program layout
            if node.source == "builtin":
                continue
            remember(node.owner_space, node.symbol.name, node.source)
        elif isinstance(node, (DefineExpr, DefunExpr)):
            remember(node.owner_space, node.name.name, "define")

    ids = {key: index for index, key in enumerate(spaces)}
    layouts: list[HIRSymbolSpaceLayout] = []
    for key, space in spaces.items():
        parent = space.parent
        parent_id = ids.get(id(parent)) if parent is not None else None
        slots = tuple(
            HIRBindingSlot(
                symbol=symbol,
                index=index,
                source=sources.get((key, symbol.name), space.sources.get(symbol.name, "define")),
            )
            for symbol, index in sorted(space.bindings.items(), key=lambda item: item[1])
        )
        layouts.append(
            HIRSymbolSpaceLayout(
                id=ids[key],
                name=space.name,
                parent=parent_id,
                slots=slots,
            )
        )
    return tuple(layouts)


class ResolveSpacesPass(Pass):
    input_kind = "hir"
    output_kind = "hir"

    def __init__(self) -> None:
        super().__init__("resolve.spaces")

    def run(self, context: PassContext) -> PassResult:
        program = cast(ProgramIR, context.input_artifact)
        layouts = collect_symbol_spaces(program)
        resolved = ProgramIR(
            body=program.body,
            diagnostics=program.diagnostics,
            symbol_spaces=layouts,
        )
        return PassResult(
            success=True,
            artifact=resolved,
            artifact_kind=self.output_kind,
        )
