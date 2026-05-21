# coding: utf-8

from __future__ import annotations

from lsprotocol import types

from qy.tools.fmt import format_source
from qy.tools.lsp.utils import full_document_range


def format_document(source: str) -> list[types.TextEdit]:
    return [
        types.TextEdit(
            range=full_document_range(source),
            new_text=format_source(source),
        )
    ]
