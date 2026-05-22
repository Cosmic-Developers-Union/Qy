# coding: utf-8

from __future__ import annotations

from lsprotocol import types

from qy.core.syntax import Chain
from qy.frontend.reader import Form
from qy.frontend.reader import ReaderSyntaxError
from qy.frontend.reader import Symbol
from qy.frontend.reader import get_span
from qy.frontend.reader import read
from qy.tools.lsp.completion import defined_name
from qy.tools.lsp.utils import span_to_range


def document_symbols_for_source(source: str) -> list[types.DocumentSymbol]:
    try:
        forms = read(source)
    except ReaderSyntaxError:
        return []
    symbols: list[types.DocumentSymbol] = []
    for form in forms:
        symbol = document_symbol_for_form(form)
        if symbol is not None:
            symbols.append(symbol)
    return symbols


def document_symbol_for_form(form: Form) -> types.DocumentSymbol | None:
    name = defined_name(form)
    if name is None:
        return None
    span = get_span(form) or name.span
    if span is None:
        return None
    kind = types.SymbolKind.Function
    if isinstance(form, Chain) and form.head == Symbol("module"):
        kind = types.SymbolKind.Module
    elif isinstance(form, Chain) and form.head == Symbol("defeffect"):
        kind = types.SymbolKind.Event
    return types.DocumentSymbol(
        name=name.name,
        kind=kind,
        range=span_to_range(span),
        selection_range=span_to_range(name.span or span),
    )
