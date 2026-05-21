# coding: utf-8

from lsprotocol import types

from qy.tools.lsp.formatting import format_document


def test_format_document():
    source = "(defun hello()body)"
    edits = format_document(source)
    assert len(edits) == 1
    assert isinstance(edits[0], types.TextEdit)
    assert edits[0].new_text != source
