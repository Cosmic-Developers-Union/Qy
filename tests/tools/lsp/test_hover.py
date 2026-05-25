# coding: utf-8

from qy.tools.lsp.hover import hover_for_source


def test_hover_for_source_builtin():
    source = "(+ 1 2)"
    hover = hover_for_source(source, 0, 1)
    assert hover is not None
    assert "+" in hover.contents.value  # ty: ignore[unresolved-attribute]


def test_hover_for_source_undefined():
    source = "(undefined-symbol)"
    hover = hover_for_source(source, 0, 2)
    assert hover is None


def test_hover_for_source_no_symbol():
    source = "(+ 1 2)"
    hover = hover_for_source(source, 0, 0)
    assert hover is None
