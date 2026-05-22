# coding: utf-8

from lsprotocol import types

from qy.frontend.reader import read
from qy.tools.lsp.completion import completion_items
from qy.tools.lsp.completion import completion_prefix_at
from qy.tools.lsp.completion import defined_name
from qy.tools.lsp.completion import snippet_completion_items


def test_snippet_completion_items():
    items = snippet_completion_items()
    assert len(items) > 0
    assert all(isinstance(item, types.CompletionItem) for item in items)
    assert all(item.kind == types.CompletionItemKind.Snippet for item in items)
    labels = [item.label for item in items]
    assert "defun form" in labels
    assert "lambda form" in labels
    assert "let form" in labels


def test_completion_items_basic():
    items = completion_items()
    assert len(items) > 0
    assert all(isinstance(item, types.CompletionItem) for item in items)


def test_completion_items_with_prefix():
    source = "(defun hello () (+ 1 2))"
    items = completion_items(source, 0, 2)
    assert len(items) > 0


def test_completion_prefix_at():
    source = "(defun hello)"
    assert completion_prefix_at(source, 0, 3) == "de"
    assert completion_prefix_at(source, 0, 1) == ""
    assert completion_prefix_at(None, None, None) == ""


def test_defined_name():
    source = "(defun hello () body)"
    forms = read(source)
    name = defined_name(forms[0])
    assert name is not None
    assert name.name == "hello"

    source = "(+ 1 2)"
    forms = read(source)
    name = defined_name(forms[0])
    assert name is None
