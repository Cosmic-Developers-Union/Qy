# coding: utf-8

from __future__ import annotations

import ast
import json
import math
from collections.abc import Iterable
from dataclasses import dataclass
from dataclasses import field

import lark

from qy.errors import QySyntaxError
from qy.errors import SourceSpan

__all__ = [
    "GRAMMAR",
    "Form",
    "ReaderSyntaxError",
    "SourceSpan",
    "SpannedTuple",
    "Symbol",
    "TupleForm",
    "form_to_tuple",
    "get_span",
    "read",
    "read_one",
    "read_one_tuple",
    "read_tuple",
    "tuple_to_form",
    "write",
    "write_program",
    "write_tuple",
    "write_tuple_program",
]


@dataclass(frozen=True, slots=True)
class Symbol:
    name: str
    span: SourceSpan | None = field(default=None, compare=False, repr=False)

    def __str__(self) -> str:
        return self.name


class SpannedTuple(tuple):
    def __new__(cls, items: Iterable[object] = (), span: SourceSpan | None = None) -> SpannedTuple:
        value = super().__new__(cls, items)
        value.span = span
        return value


type Form = Symbol | tuple["Form", ...]
type TupleAtom = Symbol | str | int | float | bool | bytes | None
type TupleForm = TupleAtom | tuple["TupleForm", ...]


GRAMMAR = r'''
?start: program

program: form*

?form: quote
    | list
    | atom

quote: "'" form

list: "(" form* ")" -> list_expr

?atom: RAW_MULTILINE_SYMBOL -> raw_multiline_symbol
    | MULTILINE_SYMBOL       -> multiline_symbol
    | RAW_QUOTED_SYMBOL      -> raw_quoted_symbol
    | QUOTED_SYMBOL          -> quoted_symbol
    | BARE_SYMBOL            -> bare_symbol

RAW_MULTILINE_SYMBOL.10: /(?s:[rR]""".*?""")/
MULTILINE_SYMBOL.9: /(?s:""".*?""")/
RAW_QUOTED_SYMBOL.8: /[rR]"[^"]*"/
QUOTED_SYMBOL.7: /"(?:\\.|[^"\\])*"/
BARE_SYMBOL: /[^()\s"';]+/

COMMENT: /;[^\n]*/

%import common.WS
%ignore WS
%ignore COMMENT
'''

_parser = lark.Lark(
    GRAMMAR,
    parser="lalr",
    maybe_placeholders=False,
    propagate_positions=True,
)


class ReaderSyntaxError(QySyntaxError):
    def __init__(
        self,
        message: str,
        *,
        line: int | None = None,
        column: int | None = None,
        span: SourceSpan | None = None,
    ) -> None:
        super().__init__(message, span=span or _span_from_line_column(line, column))


@lark.v_args(inline=True, meta=True)
class _ReaderTransformer(lark.Transformer):
    def __init__(self, source_name: str | None = None) -> None:
        super().__init__()
        self.source_name = source_name

    def program(self, meta: lark.tree.Meta, *forms: Form) -> list[Form]:
        del meta
        return list(forms)

    def quote(self, meta: lark.tree.Meta, form: Form) -> Form:
        span = self._span(meta)
        return SpannedTuple((Symbol("quote", span), form), span)

    def list_expr(self, meta: lark.tree.Meta, *forms: Form) -> Form:
        return SpannedTuple(forms, self._span(meta))

    def bare_symbol(self, meta: lark.tree.Meta, token: lark.Token) -> Symbol:
        del meta
        return Symbol(str(token), self._token_span(token))

    def quoted_symbol(self, meta: lark.tree.Meta, token: lark.Token) -> Symbol:
        del meta
        span = self._token_span(token)
        return Symbol(_decode_quoted_symbol(str(token), span), span)

    def raw_quoted_symbol(self, meta: lark.tree.Meta, token: lark.Token) -> Symbol:
        del meta
        return Symbol(str(token)[2:-1], self._token_span(token))

    def multiline_symbol(self, meta: lark.tree.Meta, token: lark.Token) -> Symbol:
        del meta
        span = self._token_span(token)
        return Symbol(_decode_quoted_symbol(str(token), span), span)

    def raw_multiline_symbol(self, meta: lark.tree.Meta, token: lark.Token) -> Symbol:
        del meta
        return Symbol(str(token)[4:-3], self._token_span(token))

    def _span(self, meta: lark.tree.Meta) -> SourceSpan:
        return SourceSpan(
            self.source_name,
            meta.line,
            meta.column,
            meta.end_line,
            meta.end_column,
        )

    def _token_span(self, token: lark.Token) -> SourceSpan:
        return SourceSpan(
            self.source_name,
            token.line,
            token.column,
            token.end_line,
            token.end_column,
        )


def read(source: str, *, source_name: str | None = None) -> list[Form]:
    try:
        tree = _parser.parse(source)
        return _ReaderTransformer(source_name).transform(tree)
    except lark.UnexpectedInput as e:
        raise ReaderSyntaxError(
            str(e),
            span=SourceSpan(source_name, e.line, e.column, e.line, e.column),
        ) from e
    except (lark.LarkError, SyntaxError, ValueError) as e:
        raise ReaderSyntaxError(str(e)) from e


def read_one(source: str, *, source_name: str | None = None) -> Form:
    forms = read(source, source_name=source_name)
    if len(forms) != 1:
        raise ReaderSyntaxError(f"expected exactly one form, got {len(forms)}")
    return forms[0]


def read_tuple(source: str) -> list[TupleForm]:
    return [form_to_tuple(form) for form in read(source)]


def read_one_tuple(source: str) -> TupleForm:
    return form_to_tuple(read_one(source))


def form_to_tuple(form: Form) -> TupleForm:
    if isinstance(form, Symbol):
        return form
    if isinstance(form, tuple):
        return tuple(form_to_tuple(item) for item in form)
    raise TypeError(f"expected qy form, got {type(form).__name__}")


def tuple_to_form(form: TupleForm) -> Form:
    if isinstance(form, Symbol):
        return form
    if isinstance(form, tuple):
        return tuple(tuple_to_form(item) for item in form)
    raise TypeError(f"expected symbolic tuple form, got literal {type(form).__name__}")


def write(form: Form) -> str:
    if isinstance(form, Symbol):
        return _encode_symbol(form.name)
    if isinstance(form, tuple):
        return f"({' '.join(write(item) for item in form)})"
    raise TypeError(f"expected qy form, got {type(form).__name__}")


def write_program(forms: Iterable[Form]) -> str:
    return "\n".join(write(form) for form in forms)


def write_tuple(form: TupleForm) -> str:
    if isinstance(form, Symbol):
        return write(form)
    if isinstance(form, tuple):
        return f"({' '.join(write_tuple(item) for item in form)})"
    return _encode_literal(form)


def write_tuple_program(forms: Iterable[TupleForm]) -> str:
    return "\n".join(write_tuple(form) for form in forms)


def get_span(value: object) -> SourceSpan | None:
    if isinstance(value, Symbol):
        return value.span
    return getattr(value, "span", None)


def _decode_quoted_symbol(token: str, span: SourceSpan | None = None) -> str:
    try:
        value = ast.literal_eval(token)
    except (SyntaxError, ValueError) as e:
        raise ReaderSyntaxError(str(e), span=span) from e
    if not isinstance(value, str):
        raise ReaderSyntaxError(f"expected quoted symbol, got {token}", span=span)
    return value


def _span_from_line_column(line: int | None, column: int | None) -> SourceSpan | None:
    if line is None and column is None:
        return None
    return SourceSpan(None, line, column, line, column)


def _encode_symbol(name: str) -> str:
    if _can_write_bare(name):
        return name
    return json.dumps(name, ensure_ascii=False)


def _can_write_bare(name: str) -> bool:
    if not name:
        return False
    return not any(char.isspace() or char in """()"';""" for char in name)


def _encode_literal(value: TupleAtom) -> str:
    if isinstance(value, str | bytes):
        raise TypeError(
            f"cannot write Python {type(value).__name__} literal as qy source; use Symbol(...)"
        )
    if value is True:
        return "true"
    if value is False:
        return "false"
    if value is None:
        return "nil"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise TypeError(f"cannot write non-finite float literal {value!r} as qy source")
        return repr(value)
    raise TypeError(f"cannot write literal {type(value).__name__} as qy source")
