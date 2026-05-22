# coding: utf-8

from __future__ import annotations

from lsprotocol import types

from qy.frontend.reader import Symbol
from qy.runtime import Qy
from qy.tools.lsp.utils import shared_instance
from qy.tools.lsp.utils import symbol_name_at


def hover_for_source(
    source: str,
    line: int,
    character: int,
    *,
    qy: Qy | None = None,
) -> types.Hover | None:
    runtime = qy or shared_instance()
    name = symbol_name_at(source, line, character)
    if name is None:
        return None
    try:
        value = runtime.env.resolve(Symbol(name))
    except Exception:
        return None

    kind = getattr(value, "kind", None)
    doc = getattr(value, "doc", "")
    if kind is None:
        doc = f"Qy value: `{type(value).__name__}`"
        kind = "value"
    return types.Hover(
        contents=types.MarkupContent(
            kind=types.MarkupKind.Markdown,
            value=f"**{name}** `{kind}`\n\n{doc}",
        )
    )
