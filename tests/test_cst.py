# coding: utf-8
"""Tests for the CST layer (cst.py and cst_parser.py)."""

from __future__ import annotations

import pytest

from qy.frontend.cst import AtomKind
from qy.frontend.cst import CstAtom
from qy.frontend.cst import CstList
from qy.frontend.cst import CstProgram
from qy.frontend.cst import collect_text
from qy.frontend.cst_parser import CstParseError
from qy.frontend.cst_parser import parse_cst


def test_parse_empty_source():
    cst = parse_cst("")
    assert cst.children == ()
    assert cst.trailing_trivia == ""


def test_parse_whitespace_only():
    cst = parse_cst("   \n  ")
    assert cst.children == ()
    assert cst.trailing_trivia == "   \n  "


def test_parse_simple_atom():
    cst = parse_cst("hello")
    assert len(cst.children) == 1
    atom = cst.children[0]
    assert isinstance(atom, CstAtom)
    assert atom.kind is AtomKind.BARE
    assert atom.text == "hello"


def test_parse_simple_list():
    cst = parse_cst("(+ 1 2)")
    assert len(cst.children) == 1
    lst = cst.children[0]
    assert isinstance(lst, CstList)
    assert len(lst.children) == 3
    assert not lst.is_dotted


def test_parse_dotted_pair():
    cst = parse_cst("(a . b)")
    lst = cst.children[0]
    assert isinstance(lst, CstList)
    assert lst.is_dotted
    assert len(lst.children) == 1  # just 'a' before the dot
    assert lst.tail is not None
    assert isinstance(lst.tail, CstAtom)
    assert lst.tail.text == "b"


def test_parse_quoted_string():
    cst = parse_cst('"hello world"')
    atom = cst.children[0]
    assert isinstance(atom, CstAtom)
    assert atom.kind is AtomKind.QUOTED
    assert atom.text == '"hello world"'


def test_parse_raw_quoted():
    cst = parse_cst(r'r"\d+"')
    atom = cst.children[0]
    assert isinstance(atom, CstAtom)
    assert atom.kind is AtomKind.RAW_QUOTED


def test_parse_tagged_literal():
    cst = parse_cst('t"hello"')
    atom = cst.children[0]
    assert isinstance(atom, CstAtom)
    assert atom.kind is AtomKind.TAGGED_QUOTED
    assert atom.text == 't"hello"'


def test_parse_multiline_string():
    cst = parse_cst('"""hello\nworld"""')
    atom = cst.children[0]
    assert isinstance(atom, CstAtom)
    assert atom.kind is AtomKind.MULTILINE


def test_parse_preserves_comments_in_trivia():
    cst = parse_cst("; comment\n(x)")
    lst = cst.children[0]
    assert isinstance(lst, CstList)
    assert "; comment" in lst.leading_trivia


def test_parse_preserves_inline_comments():
    cst = parse_cst("(define x\n  ; inline\n  42)")
    lst = cst.children[0]
    assert isinstance(lst, CstList)
    # Find the comment in one of the children's leading trivia
    has_comment = any(
        isinstance(c, CstAtom) and "; inline" in c.leading_trivia for c in lst.children
    )
    assert has_comment


def test_unclosed_paren_raises():
    with pytest.raises(CstParseError):
        parse_cst("(a b")


def test_unexpected_close_paren_raises():
    with pytest.raises(CstParseError):
        parse_cst(")")


def test_unterminated_string_raises():
    with pytest.raises(CstParseError):
        parse_cst('"unterminated')


def test_dot_with_no_tail_raises():
    with pytest.raises(CstParseError):
        parse_cst("(a .)")


def test_collect_text_roundtrip_simple():
    sources = [
        "(+ 1 2)",
        "; comment\n(define x 42)\n",
        "(a . b)",
        "(a b . c)",
        '"hello"',
        't"hello"',
        '"""multi\nline"""',
        "  ; just a comment\n  ",
        "",
    ]
    for src in sources:
        cst = parse_cst(src)
        assert collect_text(cst) == src, f"roundtrip failed for {src!r}"


def test_collect_text_roundtrip_complex():
    src = """; head comment
(define foo
  ; inline comment
  (lambda (x) (+ x 1)))

(foo 41)  ; trailing comment
"""
    cst = parse_cst(src)
    assert collect_text(cst) == src


def test_nested_lists():
    cst = parse_cst("(a (b (c d)) e)")
    outer = cst.children[0]
    assert isinstance(outer, CstList)
    assert len(outer.children) == 3
    middle = outer.children[1]
    assert isinstance(middle, CstList)


def test_trivia_attribution():
    cst = parse_cst("foo bar")
    foo = cst.children[0]
    bar = cst.children[1]
    assert foo.leading_trivia == ""
    assert bar.leading_trivia == " "


def test_close_paren_trivia_preserved():
    cst = parse_cst("(a\n  )")
    lst = cst.children[0]
    assert isinstance(lst, CstList)
    assert "\n  " in lst.close_trivia
    # Roundtrip
    assert collect_text(cst) == "(a\n  )"


def test_program_span():
    cst = parse_cst("(+ 1 2)\n")
    assert isinstance(cst, CstProgram)
    assert cst.span.start_line == 1
    assert cst.span.start_column == 1


def test_atom_span():
    cst = parse_cst("  hello")
    atom = cst.children[0]
    assert atom.span.start_column == 3
    assert atom.span.end_column == 8
