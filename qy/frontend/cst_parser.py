# coding: utf-8
"""CST parser: Source → CstProgram (trivia-preserving)。.

手写 lexer + 递归下降 parser。不使用 Lark 的 %ignore，
以完整保留 whitespace 和 comment 信息。

设计：
- 每个 node 携带 leading_trivia (前置 whitespace/comment)。
- CstProgram.trailing_trivia 保存文件末尾的 trivia。
- Roundtrip: collect_text(parse_cst(s)) == s 对所有合法输入成立。
"""

from __future__ import annotations

from qy.errors import QySyntaxError
from qy.frontend.cst import AtomKind
from qy.frontend.cst import CstAtom
from qy.frontend.cst import CstList
from qy.frontend.cst import CstNode
from qy.frontend.cst import CstProgram
from qy.source.span import SourceSpan

__all__ = ["CstParseError", "parse_cst"]


class CstParseError(QySyntaxError):
    pass


def parse_cst(source: str, *, source_name: str | None = None) -> CstProgram:
    """Parse source into a CST (trivia-preserving)."""
    parser = _CstParser(source, source_name)
    return parser.parse_program()


class _CstParser:
    def __init__(self, source: str, source_name: str | None) -> None:
        self._source = source
        self._source_name = source_name
        self._pos = 0
        self._line = 1
        self._col = 1

    def parse_program(self) -> CstProgram:
        start_span = self._current_span()
        children: list[CstNode] = []
        while True:
            trivia = self._consume_trivia()
            if self._at_end():
                end_span = self._current_span()
                return CstProgram(
                    children=tuple(children),
                    trailing_trivia=trivia,
                    span=self._span_from(start_span, end_span),
                )
            node = self._parse_node(trivia)
            children.append(node)

    def _parse_node(self, leading_trivia: str) -> CstNode:
        ch = self._peek()
        if ch == "(":
            return self._parse_list(leading_trivia)
        if ch == ")":
            raise CstParseError(
                "unexpected ')'",
                span=self._make_span(self._line, self._col, self._line, self._col + 1),
            )
        return self._parse_atom(leading_trivia)

    def _parse_list(self, leading_trivia: str) -> CstList:
        start_line, start_col = self._line, self._col
        self._advance()  # consume '('

        children: list[CstNode] = []
        dot_trivia: str = ""
        tail: CstNode | None = None
        close_trivia: str = ""

        while True:
            trivia = self._consume_trivia()
            if self._at_end():
                raise CstParseError(
                    "unclosed '('",
                    span=self._make_span(start_line, start_col, self._line, self._col),
                )
            ch = self._peek()
            if ch == ")":
                close_trivia = trivia
                self._advance()  # consume ')'
                end_line, end_col = self._line, self._col
                return CstList(
                    children=tuple(children),
                    span=self._make_span(start_line, start_col, end_line, end_col),
                    leading_trivia=leading_trivia,
                    dot_trivia=dot_trivia,
                    tail=tail,
                    close_trivia=close_trivia,
                )
            if self._is_dot():
                dot_trivia = trivia
                self._advance()  # consume '.'
                # Parse the tail form
                tail_trivia = self._consume_trivia()
                if self._at_end() or self._peek() == ")":
                    raise CstParseError(
                        "expected form after '.'",
                        span=self._make_span(self._line, self._col, self._line, self._col),
                    )
                tail = self._parse_node(tail_trivia)
                continue
            node = self._parse_node(trivia)
            children.append(node)

    def _parse_atom(self, leading_trivia: str) -> CstAtom:
        if self._looking_at_multiline():
            return self._parse_multiline_atom(leading_trivia)
        if self._looking_at_quoted():
            return self._parse_quoted_atom(leading_trivia)
        return self._parse_bare_atom(leading_trivia)

    def _parse_bare_atom(self, leading_trivia: str) -> CstAtom:
        start_line, start_col = self._line, self._col
        start = self._pos
        while not self._at_end():
            ch = self._peek()
            if ch in '() \t\n\r;"':
                break
            self._advance()
        text = self._source[start : self._pos]
        if not text:
            raise CstParseError(
                "empty atom",
                span=self._make_span(start_line, start_col, self._line, self._col),
            )
        return CstAtom(
            kind=AtomKind.BARE,
            text=text,
            span=self._make_span(start_line, start_col, self._line, self._col),
            leading_trivia=leading_trivia,
        )

    def _parse_quoted_atom(self, leading_trivia: str) -> CstAtom:
        start_line, start_col = self._line, self._col
        start = self._pos

        # Consume prefix before the opening quote
        while self._peek() != '"':
            self._advance()

        prefix = self._source[start : self._pos]
        kind: AtomKind
        if prefix.lower() == "r":
            kind = AtomKind.RAW_QUOTED
        elif prefix == "":
            kind = AtomKind.QUOTED
        else:
            kind = AtomKind.TAGGED_QUOTED

        # Consume opening "
        self._advance()

        # Consume string body
        is_raw = prefix.lower() == "r"
        while not self._at_end():
            ch = self._peek()
            if ch == "\\" and not is_raw:
                self._advance()
                if not self._at_end():
                    self._advance()
            elif ch == '"':
                self._advance()
                break
            else:
                self._advance()
        else:
            raise CstParseError(
                "unterminated string",
                span=self._make_span(start_line, start_col, self._line, self._col),
            )

        text = self._source[start : self._pos]
        return CstAtom(
            kind=kind,
            text=text,
            span=self._make_span(start_line, start_col, self._line, self._col),
            leading_trivia=leading_trivia,
        )

    def _parse_multiline_atom(self, leading_trivia: str) -> CstAtom:
        start_line, start_col = self._line, self._col
        start = self._pos

        # Consume prefix up to the first "
        while self._peek() != '"':
            self._advance()

        prefix = self._source[start : self._pos]
        kind: AtomKind
        if prefix.lower() == "r":
            kind = AtomKind.RAW_MULTILINE
        elif prefix == "":
            kind = AtomKind.MULTILINE
        else:
            kind = AtomKind.TAGGED_MULTILINE

        # Consume opening triple-quote
        self._advance()
        self._advance()
        self._advance()

        # Find closing triple-quote
        while not self._at_end():
            if self._peek() == '"' and self._lookahead(1) == '"' and self._lookahead(2) == '"':
                self._advance()
                self._advance()
                self._advance()
                break
            self._advance()
        else:
            raise CstParseError(
                "unterminated multiline string",
                span=self._make_span(start_line, start_col, self._line, self._col),
            )

        text = self._source[start : self._pos]
        return CstAtom(
            kind=kind,
            text=text,
            span=self._make_span(start_line, start_col, self._line, self._col),
            leading_trivia=leading_trivia,
        )

    def _looking_at_multiline(self) -> bool:
        """Check if current position starts a multiline string."""
        if self._pos >= len(self._source):
            return False
        # Direct triple-quote
        if (
            self._source[self._pos] == '"'
            and self._pos + 2 < len(self._source)
            and self._source[self._pos + 1] == '"'
            and self._source[self._pos + 2] == '"'
        ):
            return True
        # Prefixed: scan for triple-quote within atom chars
        i = self._pos
        while i < len(self._source) and self._source[i] not in "() \t\n\r;":
            if self._source[i] == '"':
                return (
                    i + 2 < len(self._source)
                    and self._source[i + 1] == '"'
                    and self._source[i + 2] == '"'
                )
            i += 1
        return False

    def _looking_at_quoted(self) -> bool:
        """Check if current position starts a quoted string (with or without prefix)."""
        if self._pos >= len(self._source):
            return False
        if self._source[self._pos] == '"':
            return True
        # Prefixed: scan for quote within atom chars (excluding delimiters but NOT ")
        i = self._pos
        while i < len(self._source) and self._source[i] not in "() \t\n\r;":
            if self._source[i] == '"':
                return True
            i += 1
        return False

    def _is_dot(self) -> bool:
        """Check if current position is a standalone dot (. followed by delimiter)."""
        if self._peek() != ".":
            return False
        next_pos = self._pos + 1
        if next_pos >= len(self._source):
            return True
        next_ch = self._source[next_pos]
        return next_ch in '() \t\n\r;"'

    def _consume_trivia(self) -> str:
        """Consume whitespace and comments, return the raw text."""
        start = self._pos
        while not self._at_end():
            ch = self._peek()
            if ch in " \t\n\r":
                self._advance()
            elif ch == ";":
                while not self._at_end() and self._peek() != "\n":
                    self._advance()
            else:
                break
        return self._source[start : self._pos]

    def _peek(self) -> str:
        if self._pos >= len(self._source):
            return ""
        return self._source[self._pos]

    def _lookahead(self, offset: int) -> str:
        idx = self._pos + offset
        if idx >= len(self._source):
            return ""
        return self._source[idx]

    def _advance(self) -> str:
        if self._pos >= len(self._source):
            return ""
        ch = self._source[self._pos]
        self._pos += 1
        if ch == "\n":
            self._line += 1
            self._col = 1
        else:
            self._col += 1
        return ch

    def _at_end(self) -> bool:
        return self._pos >= len(self._source)

    def _current_span(self) -> SourceSpan:
        return SourceSpan(self._source_name, self._line, self._col, self._line, self._col)

    def _make_span(
        self, start_line: int, start_col: int, end_line: int, end_col: int
    ) -> SourceSpan:
        return SourceSpan(self._source_name, start_line, start_col, end_line, end_col)

    def _span_from(self, start: SourceSpan, end: SourceSpan) -> SourceSpan:
        return SourceSpan(
            self._source_name,
            start.start_line,
            start.start_column,
            end.end_line,
            end.end_column,
        )
