# coding: utf-8

from __future__ import annotations

import ast
import json
import math
from collections.abc import Iterable
from dataclasses import dataclass

import lark

__all__ = [
    "GRAMMAR",
    "Form",
    "ReaderSyntaxError",
    "Symbol",
    "TupleForm",
    "form_to_tuple",
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

    def __str__(self) -> str:
        return self.name


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

_parser = lark.Lark(GRAMMAR, parser="lalr", maybe_placeholders=False)


class ReaderSyntaxError(Exception):
    def __init__(
        self,
        message: str,
        *,
        line: int | None = None,
        column: int | None = None,
    ) -> None:
        super().__init__(message)
        self.line = line
        self.column = column


@lark.v_args(inline=True)
class _ReaderTransformer(lark.Transformer):
    def program(self, *forms: Form) -> list[Form]:
        return list(forms)

    def quote(self, form: Form) -> Form:
        return (Symbol("quote"), form)

    def list_expr(self, *forms: Form) -> Form:
        return forms

    def bare_symbol(self, token: lark.Token) -> Symbol:
        return Symbol(str(token))

    def quoted_symbol(self, token: lark.Token) -> Symbol:
        return Symbol(_decode_quoted_symbol(str(token)))

    def raw_quoted_symbol(self, token: lark.Token) -> Symbol:
        return Symbol(str(token)[2:-1])

    def multiline_symbol(self, token: lark.Token) -> Symbol:
        return Symbol(_decode_quoted_symbol(str(token)))

    def raw_multiline_symbol(self, token: lark.Token) -> Symbol:
        return Symbol(str(token)[4:-3])


_transformer = _ReaderTransformer()


def read(source: str) -> list[Form]:
    try:
        tree = _parser.parse(source)
        return _transformer.transform(tree)
    except lark.UnexpectedInput as e:
        raise ReaderSyntaxError(str(e), line=e.line, column=e.column) from e
    except (lark.LarkError, SyntaxError, ValueError) as e:
        raise ReaderSyntaxError(str(e)) from e


def read_one(source: str) -> Form:
    forms = read(source)
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


def _decode_quoted_symbol(token: str) -> str:
    value = ast.literal_eval(token)
    if not isinstance(value, str):
        raise ReaderSyntaxError(f"expected quoted symbol, got {token}")
    return value


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
