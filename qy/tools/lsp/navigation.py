# coding: utf-8
"""LSP 导航能力：跳转定义与查找引用。.

两者都基于 `qy.tools.lsp.facts`（canonical frontend + HIR），因此与
`qy check`、analyzer、CLI 读取同一份事实，不重新解释源码。

当前范围：

- ``definition_location``：命中 lexical binding（define / let / 参数 / handler
  参数 / defeffect）时返回其定义点；否则回退到实例 env 中可见的绑定（无源码位置）。
- ``reference_locations``：返回文档内该 symbol 的全部 HIR 出现点（含定义点）。

禁止：
- 不得在这里定义作用域或解析规则（属于 canonical frontend / HIR）。
"""

from __future__ import annotations

from lsprotocol import types

from qy.runtime import Qy
from qy.tools.lsp.facts import symbol_occurrences
from qy.tools.lsp.utils import shared_instance
from qy.tools.lsp.utils import span_to_range
from qy.tools.lsp.utils import symbol_name_at

__all__ = ["definition_location", "reference_locations"]


def _name_at(source: str, line: int, character: int) -> str | None:
    return symbol_name_at(source, line, character)


def definition_location(
    source: str,
    line: int,
    character: int,
    uri: str,
    *,
    qy: Qy | None = None,
) -> types.Location | None:
    """Return the definition site of the symbol at the cursor, if known."""
    runtime = qy or shared_instance()
    name = _name_at(source, line, character)
    if name is None:
        return None

    candidates = [
        occurrence
        for occurrence in symbol_occurrences(source, qy=runtime)
        if occurrence.is_definition
        and occurrence.name == name
        and (occurrence.span.start_line or 1) <= line + 1
    ]
    if not candidates:
        return None
    target = max(candidates, key=lambda occurrence: occurrence.span.start_line or 0)
    return types.Location(uri=uri, range=span_to_range(target.span))


def reference_locations(
    source: str,
    line: int,
    character: int,
    uri: str,
    *,
    qy: Qy | None = None,
    include_declaration: bool = True,
) -> list[types.Location]:
    """Return every HIR occurrence of the symbol at the cursor."""
    runtime = qy or shared_instance()
    name = _name_at(source, line, character)
    if name is None:
        return []

    locations: list[types.Location] = []
    for occurrence in symbol_occurrences(source, qy=runtime):
        if occurrence.name != name:
            continue
        if occurrence.is_definition and not include_declaration:
            continue
        locations.append(types.Location(uri=uri, range=span_to_range(occurrence.span)))
    return locations
