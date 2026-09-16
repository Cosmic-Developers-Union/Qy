# coding: utf-8

from __future__ import annotations

from lsprotocol import types

from qy.core.syntax import Symbol
from qy.runtime import Qy
from qy.tools.lsp.facts import document_locals
from qy.tools.lsp.utils import shared_instance
from qy.tools.lsp.utils import symbol_name_at


def _local_binding_at(source: str, name: str, line: int, *, qy: Qy | None = None):
    """在光标之前、名字匹配的 lexical binding 中取最靠后的一个（最内层近似）。."""
    candidates = [
        binding
        for binding in document_locals(source, qy=qy)
        if binding.name == name and binding.line is not None and binding.line <= line + 1
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda binding: binding.line or 0)


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

    local = _local_binding_at(source, name, line, qy=qy)
    if local is not None:
        return types.Hover(
            contents=types.MarkupContent(
                kind=types.MarkupKind.Markdown,
                value=f"**{local.name}** `local binding` ({local.source})",
            )
        )

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
