# coding: utf-8
"""Tests for reader macro registry and dispatch."""

from __future__ import annotations

import pytest

from qy.frontend.cst import CstAtom
from qy.frontend.reader import Form
from qy.frontend.reader import Symbol
from qy.frontend.reader import parse_cst
from qy.frontend.reader import read_cst
from qy.frontend.reader_macros import ReaderMacroRegistry
from qy.frontend.reader_macros import default_registry


def test_default_registry_is_empty():
    registry = default_registry()
    assert registry.tags() == frozenset()


def test_registry_register_and_lookup():
    registry = ReaderMacroRegistry()

    def handler(atom: CstAtom) -> Form:
        return Symbol("placeholder", atom.span)

    registry.register("mytag", handler, doc="test macro")
    entry = registry.lookup("mytag")
    assert entry is not None
    assert entry.tag == "mytag"
    assert entry.doc == "test macro"


def test_registry_duplicate_register_raises():
    registry = ReaderMacroRegistry()

    def handler(atom: CstAtom) -> Form:
        return Symbol("x")

    registry.register("tag", handler)
    with pytest.raises(ValueError):
        registry.register("tag", handler)


def test_registry_contains():
    registry = ReaderMacroRegistry()

    def handler(atom: CstAtom) -> Form:
        return Symbol("x")

    registry.register("foo", handler)
    assert "foo" in registry
    assert "bar" not in registry


def test_registry_tags():
    registry = ReaderMacroRegistry()

    def handler(atom: CstAtom) -> Form:
        return Symbol("x")

    registry.register("foo", handler)
    registry.register("bar", handler)
    assert registry.tags() == frozenset({"foo", "bar"})


def test_unregistered_tag_uses_default_behavior():
    """Without a registered macro, tagged literals expand to (tag (quote literal))."""
    cst = parse_cst('t"hello"')
    forms = read_cst(cst)
    # Default: (t (quote "hello"))
    assert len(forms) == 1


def test_registered_tag_uses_macro():
    """A registered handler replaces the default behavior."""
    registry = ReaderMacroRegistry()

    def upper_handler(atom: CstAtom) -> Form:
        # text = 'upper"hello"'; uppercase the literal portion
        text = atom.text
        quote_idx = text.index('"')
        return Symbol(text[quote_idx:].upper(), atom.span)

    registry.register("upper", upper_handler)

    cst = parse_cst('upper"hello"')
    forms = read_cst(cst, registry=registry)
    assert len(forms) == 1
    assert isinstance(forms[0], Symbol)
    assert forms[0].name == '"HELLO"'


def test_handler_receives_full_atom():
    """The handler is given the full CstAtom including span and kind."""
    registry = ReaderMacroRegistry()
    captured: list[CstAtom] = []

    def handler(atom: CstAtom) -> Form:
        captured.append(atom)
        return Symbol("ok", atom.span)

    registry.register("capture", handler)
    cst = parse_cst('capture"data"')
    read_cst(cst, registry=registry)
    assert len(captured) == 1
    assert captured[0].text == 'capture"data"'
    assert captured[0].span is not None


def test_macro_only_fires_for_tagged_atoms():
    """Bare/quoted/list atoms are not affected by reader macros."""
    registry = ReaderMacroRegistry()
    fired = []

    def handler(atom: CstAtom) -> Form:
        fired.append(atom)
        return Symbol("x", atom.span)

    registry.register("foo", handler)

    # Plain symbol "foo" should NOT fire
    cst = parse_cst("foo")
    read_cst(cst, registry=registry)
    assert fired == []

    # List (foo bar) should NOT fire
    cst = parse_cst("(foo bar)")
    read_cst(cst, registry=registry)
    assert fired == []

    # Tagged literal foo"x" SHOULD fire
    cst = parse_cst('foo"x"')
    read_cst(cst, registry=registry)
    assert len(fired) == 1


def test_multiline_tagged_dispatches():
    """Tagged multiline strings also go through reader macros."""
    registry = ReaderMacroRegistry()
    fired = []

    def handler(atom: CstAtom) -> Form:
        fired.append(atom.kind.value)
        return Symbol("ok", atom.span)

    registry.register("sql", handler)
    cst = parse_cst('sql"""select *\nfrom t"""')
    read_cst(cst, registry=registry)
    assert "tagged_multiline" in fired
