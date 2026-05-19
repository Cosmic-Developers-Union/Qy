# coding: utf-8
"""Qy 前端 Reader 实现。

source -> raw AST 解析器，基于 Lark S-expression 解析器。

raw AST 由以下组成：
- Symbol：带 span 的符号
- SpannedTuple：带 span 的 tuple
- DottedTuple：带 span 的 dotted pair

当前：
- 这是主要的 reader 实现位置。
- Surface dialect 展开嵌入在此模块中，后续应拆分为 qy/frontend/surface.py。
- raw AST 仍在从 Python tuple 向 immutable chain 迁移中。

禁止：
- 不得提前将 number/string 等 literal 物化为 Python 值。
- 不得在这里实现 runtime evaluation。
"""

from __future__ import annotations

import ast
import json
import math
from collections.abc import Iterable
from dataclasses import dataclass
from dataclasses import field
from typing import cast

import lark

from qy.errors import QySyntaxError
from qy.errors import SourceSpan
from qy.values import QY_EMPTY_LIST
from qy.values import QY_NIL
from qy.values import QY_T
from qy.values import QyCons

__all__ = [
    "GRAMMAR",
    "DottedTuple",
    "Form",
    "ReaderSyntaxError",
    "SourceSpan",
    "SpannedTuple",
    "Symbol",
    "TupleForm",
    "_decode_string_symbol",
    "_is_string_symbol",
    "expand_surface_dialect",
    "form_to_tuple",
    "get_span",
    "read",
    "read_one",
    "read_one_tuple",
    "read_raw",
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
    span: SourceSpan | None

    def __new__(cls, items: Iterable[object] = (), span: SourceSpan | None = None) -> SpannedTuple:
        value = super().__new__(cls, items)
        value.span = span
        return value


class DottedTuple(tuple):
    tail: object
    span: SourceSpan | None

    def __new__(
        cls,
        items: Iterable[object] = (),
        tail: object = None,
        span: SourceSpan | None = None,
    ) -> DottedTuple:
        value = super().__new__(cls, items)
        value.tail = tail
        value.span = span
        return value


type Form = Symbol | tuple["Form", ...]
type TupleAtom = Symbol | str | int | float | bool | bytes | None
type TupleForm = TupleAtom | tuple["TupleForm", ...]


GRAMMAR = r'''
?start: program

program: form*

?form: list
    | atom

list: "(" form* (DOT form)? ")" -> list_expr

?atom: RAW_MULTILINE_SYMBOL -> raw_multiline_symbol
    | TAGGED_MULTILINE_SYMBOL -> tagged_multiline_symbol
    | MULTILINE_SYMBOL       -> multiline_symbol
    | RAW_QUOTED_SYMBOL      -> raw_quoted_symbol
    | TAGGED_QUOTED_SYMBOL   -> tagged_quoted_symbol
    | QUOTED_SYMBOL          -> quoted_symbol
    | BARE_SYMBOL            -> bare_symbol

RAW_MULTILINE_SYMBOL.12: /(?s:[rR]""".*?""")/
TAGGED_MULTILINE_SYMBOL.11: /(?s:[^()\s"';`,@]+""".*?""")/
MULTILINE_SYMBOL.10: /(?s:""".*?""")/
RAW_QUOTED_SYMBOL.9: /[rR]"[^"]*"/
TAGGED_QUOTED_SYMBOL.8: /[^()\s"';`,@]+"(?:\\.|[^"\\])*"/
QUOTED_SYMBOL.7: /"(?:\\.|[^"\\])*"/
DOT.13: "."
BARE_SYMBOL: /[^()\s";]+/

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

    def list_expr(self, meta: lark.tree.Meta, *items: object) -> Form:
        span = self._span(meta)
        dot_index = _dot_index(items)
        if dot_index is None:
            return SpannedTuple(items, span)
        if dot_index == 0:
            raise ReaderSyntaxError("dotted pair must have a head before .", span=span)
        if dot_index != len(items) - 2:
            raise ReaderSyntaxError("dotted pair must have exactly one tail after .", span=span)
        return DottedTuple(items[:dot_index], items[dot_index + 1], span)

    def bare_symbol(self, meta: lark.tree.Meta, token: lark.Token) -> Symbol:
        del meta
        return Symbol(str(token), self._token_span(token))

    def quoted_symbol(self, meta: lark.tree.Meta, token: lark.Token) -> Symbol:
        del meta
        span = self._token_span(token)
        return Symbol(str(token), span)

    def raw_quoted_symbol(self, meta: lark.tree.Meta, token: lark.Token) -> Symbol:
        del meta
        span = self._token_span(token)
        return Symbol(str(token), span)

    def tagged_quoted_symbol(self, meta: lark.tree.Meta, token: lark.Token) -> Form:
        del meta
        return self._tagged_literal(token)

    def multiline_symbol(self, meta: lark.tree.Meta, token: lark.Token) -> Symbol:
        del meta
        span = self._token_span(token)
        return Symbol(str(token), span)

    def raw_multiline_symbol(self, meta: lark.tree.Meta, token: lark.Token) -> Symbol:
        del meta
        span = self._token_span(token)
        return Symbol(str(token), span)

    def tagged_multiline_symbol(self, meta: lark.tree.Meta, token: lark.Token) -> Form:
        del meta
        return self._tagged_literal(token)

    def _tagged_literal(self, token: lark.Token) -> Form:
        span = self._token_span(token)
        tag, literal = _split_tagged_literal(str(token), span)
        return SpannedTuple(
            (
                Symbol(tag, span),
                SpannedTuple(
                    (
                        Symbol("quote", span),
                        Symbol(literal, span),
                    ),
                    span,
                ),
            ),
            span,
        )

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


def read_raw(source: str, *, source_name: str | None = None) -> list[Form]:
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


def expand_surface_dialect(forms: list[Form]) -> list[Form]:
    """Expand surface dialect syntax in a list of raw forms.

    Transforms reader sugar into canonical forms:
    - ``'x`` (prefix quote symbol) -> ``(quote x)``
    - ``'x`` (leading-quote symbol) -> ``(quote x)``
    - ``,x`` inside quasiquote -> ``(unquote x)``
    - ``,@x`` inside quasiquote -> ``(unquote-splicing x)``

    This is a pure function: it does not parse source, only transforms
    already-parsed raw forms produced by ``read_raw()``.
    """
    return _expand_surface_program(forms)


def read(source: str, *, source_name: str | None = None) -> list[Form]:
    return expand_surface_dialect(read_raw(source, source_name=source_name))


def read_one(source: str, *, source_name: str | None = None) -> Form:
    forms = read(source, source_name=source_name)
    if len(forms) != 1:
        raise ReaderSyntaxError(f"expected exactly one form, got {len(forms)}")
    return forms[0]


def _expand_surface_program(forms: list[Form]) -> list[Form]:
    return list(_expand_surface_sequence(tuple(forms), in_quasiquote=False))


def _expand_surface_form(form: Form, *, in_quasiquote: bool) -> Form:
    if isinstance(form, Symbol):
        expanded = _expand_surface_symbol(form, in_quasiquote=in_quasiquote)
        if expanded is not form:
            return expanded
        return form
    if isinstance(form, DottedTuple):
        return _expand_surface_dotted_tuple(form, in_quasiquote=in_quasiquote)
    if isinstance(form, tuple):
        return _expand_surface_tuple(form, in_quasiquote=in_quasiquote)
    return form


def _expand_surface_sequence(forms: tuple[Form, ...], *, in_quasiquote: bool) -> tuple[Form, ...]:
    expanded: list[Form] = []
    index = 0
    while index < len(forms):
        form = forms[index]
        if (
            isinstance(form, Symbol)
            and form.name == "'"
            and index + 1 < len(forms)
            and _forms_are_adjacent(form, forms[index + 1])
        ):
            expanded.append(
                _surface_call(
                    "quote",
                    (_expand_surface_form(forms[index + 1], in_quasiquote=in_quasiquote),),
                    span=_combine_spans(form, forms[index + 1]),
                )
            )
            index += 2
            continue
        expanded.append(_expand_surface_form(form, in_quasiquote=in_quasiquote))
        index += 1
    return tuple(expanded)


def _expand_surface_tuple(form: tuple[Form, ...], *, in_quasiquote: bool) -> Form:
    if not form:
        return SpannedTuple((), get_span(form))
    head = form[0]
    if not isinstance(head, Symbol):
        return SpannedTuple(
            _expand_surface_sequence(form, in_quasiquote=in_quasiquote), get_span(form)
        )

    match head.name:
        case "define":
            return _expand_define_surface(form, in_quasiquote=in_quasiquote)
        case "defun" | "macro":
            return _expand_named_body_surface(form, in_quasiquote=in_quasiquote)
        case "lambda":
            return _expand_lambda_surface(form, in_quasiquote=in_quasiquote)
        case "let":
            return _expand_let_surface(form, in_quasiquote=in_quasiquote)
        case "defeffect" | "exports" | "from" | "import":
            return SpannedTuple(form, get_span(form))
        case "module":
            if len(form) <= 2:
                return SpannedTuple(form, get_span(form))
            body = _expand_surface_sequence(tuple(form[2:]), in_quasiquote=in_quasiquote)
            return SpannedTuple((form[0], form[1], *body), get_span(form))
        case "quasiquote":
            if len(form) != 2:
                return SpannedTuple(
                    _expand_surface_sequence(form, in_quasiquote=in_quasiquote), get_span(form)
                )
            return SpannedTuple(
                (
                    form[0],
                    _expand_surface_form(form[1], in_quasiquote=True),
                ),
                get_span(form),
            )

    return SpannedTuple(_expand_surface_sequence(form, in_quasiquote=in_quasiquote), get_span(form))


def _expand_surface_dotted_tuple(form: DottedTuple, *, in_quasiquote: bool) -> DottedTuple:
    return DottedTuple(
        _expand_surface_sequence(tuple(form), in_quasiquote=in_quasiquote),
        _expand_surface_form(cast(Form, form.tail), in_quasiquote=in_quasiquote),
        get_span(form),
    )


def _expand_define_surface(form: tuple[Form, ...], *, in_quasiquote: bool) -> Form:
    if len(form) <= 2:
        return SpannedTuple(form, get_span(form))
    values = _expand_surface_sequence(tuple(form[2:]), in_quasiquote=in_quasiquote)
    return SpannedTuple((form[0], form[1], *values), get_span(form))


def _expand_named_body_surface(form: tuple[Form, ...], *, in_quasiquote: bool) -> Form:
    if len(form) <= 3:
        return SpannedTuple(form, get_span(form))
    body = _expand_surface_sequence(tuple(form[3:]), in_quasiquote=in_quasiquote)
    return SpannedTuple((form[0], form[1], form[2], *body), get_span(form))


def _expand_lambda_surface(form: tuple[Form, ...], *, in_quasiquote: bool) -> Form:
    if len(form) <= 2:
        return SpannedTuple(form, get_span(form))
    body = _expand_surface_sequence(tuple(form[2:]), in_quasiquote=in_quasiquote)
    return SpannedTuple((form[0], form[1], *body), get_span(form))


def _expand_let_surface(form: tuple[Form, ...], *, in_quasiquote: bool) -> Form:
    if len(form) <= 2:
        return SpannedTuple(form, get_span(form))
    bindings = form[1]
    if isinstance(bindings, tuple):
        bindings = SpannedTuple(
            (
                _expand_let_binding_surface(binding, in_quasiquote=in_quasiquote)
                if isinstance(binding, tuple)
                else binding
                for binding in bindings
            ),
            get_span(bindings),
        )
    body = _expand_surface_sequence(tuple(form[2:]), in_quasiquote=in_quasiquote)
    return SpannedTuple((form[0], bindings, *body), get_span(form))


def _expand_let_binding_surface(binding: tuple[Form, ...], *, in_quasiquote: bool) -> Form:
    if len(binding) <= 1:
        return SpannedTuple(binding, get_span(binding))
    values = _expand_surface_sequence(tuple(binding[1:]), in_quasiquote=in_quasiquote)
    return SpannedTuple((binding[0], *values), get_span(binding))


def _expand_surface_symbol(symbol: Symbol, *, in_quasiquote: bool) -> Form:
    if symbol.name.startswith("'") and len(symbol.name) > 1:
        quoted = Symbol(symbol.name[1:], symbol.span)
        return _surface_call(
            "quote",
            (_expand_surface_form(quoted, in_quasiquote=in_quasiquote),),
            span=symbol.span,
        )
    if in_quasiquote and symbol.name.startswith(",@") and len(symbol.name) > 2:
        return _surface_call(
            "unquote-splicing",
            (_expand_surface_form(Symbol(symbol.name[2:], symbol.span), in_quasiquote=False),),
            span=symbol.span,
        )
    if (
        in_quasiquote
        and symbol.name.startswith(",")
        and len(symbol.name) > 1
        and not symbol.name.startswith(",@")
    ):
        return _surface_call(
            "unquote",
            (_expand_surface_form(Symbol(symbol.name[1:], symbol.span), in_quasiquote=False),),
            span=symbol.span,
        )
    return symbol


def _surface_call(name: str, args: tuple[Form, ...], *, span: SourceSpan | None) -> Form:
    return SpannedTuple((Symbol(name, span), *args), span)


def _forms_are_adjacent(left: Form, right: Form) -> bool:
    left_span = get_span(left)
    right_span = get_span(right)
    return (
        left_span is not None
        and right_span is not None
        and left_span.source == right_span.source
        and left_span.end_line == right_span.start_line
        and left_span.end_column == right_span.start_column
    )


def _combine_spans(left: Form, right: Form) -> SourceSpan | None:
    left_span = get_span(left)
    right_span = get_span(right)
    if left_span is None:
        return right_span
    if right_span is None:
        return left_span
    if left_span.source != right_span.source:
        return left_span
    return SourceSpan(
        left_span.source,
        left_span.start_line,
        left_span.start_column,
        right_span.end_line,
        right_span.end_column,
    )


def read_tuple(source: str) -> list[TupleForm]:
    return [form_to_tuple(form) for form in read(source)]


def read_one_tuple(source: str) -> TupleForm:
    return form_to_tuple(read_one(source))


def form_to_tuple(form: Form) -> TupleForm:
    if isinstance(form, Symbol):
        if _is_string_symbol(form.name):
            return _decode_string_symbol(form)
        return form
    if isinstance(form, DottedTuple):
        return (
            *tuple(form_to_tuple(item) for item in form),
            Symbol("."),
            form_to_tuple(cast(Form, form.tail)),
        )
    if isinstance(form, tuple):
        return tuple(form_to_tuple(item) for item in form)
    raise TypeError(f"expected qy form, got {type(form).__name__}")


def tuple_to_form(form: TupleForm) -> Form:
    if isinstance(form, str):
        return Symbol(json.dumps(form, ensure_ascii=False))
    if isinstance(form, Symbol):
        return form
    if isinstance(form, tuple):
        return tuple(tuple_to_form(item) for item in form)
    raise TypeError(f"expected symbolic tuple form, got literal {type(form).__name__}")


def write(form: Form) -> str:
    if isinstance(form, Symbol):
        if _is_string_symbol(form.name):
            return form.name
        return _encode_symbol(form.name)
    if isinstance(form, DottedTuple):
        head = " ".join(write(item) for item in form)
        return f"({head} . {write(cast(Form, form.tail))})"
    if isinstance(form, tuple):
        if _is_surface_quote(form):
            return "'" + write(form[1])
        if _is_surface_quasiquote(form):
            return "`" + write(form[1])
        return f"({' '.join(write(item) for item in form)})"
    raise TypeError(f"expected qy form, got {type(form).__name__}")


def write_program(forms: Iterable[Form]) -> str:
    return "\n".join(write(form) for form in forms)


def write_tuple(form: TupleForm) -> str:
    if form is QY_NIL:
        return "nil"
    if form is QY_T:
        return "T"
    if isinstance(form, QyCons):
        return _write_cons(form)
    if isinstance(form, str):
        return json.dumps(form, ensure_ascii=False)
    if isinstance(form, Symbol):
        return write(form)
    if isinstance(form, DottedTuple):
        head = " ".join(write_tuple(item) for item in form)
        return f"({head} . {write_tuple(cast(TupleForm, form.tail))})"
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


def _is_string_symbol(name: str) -> bool:
    return name.startswith('"') or name.startswith('r"')


def _decode_string_symbol(symbol: Symbol) -> str:
    return cast(str, ast.literal_eval(symbol.name))


def _split_tagged_literal(token: str, span: SourceSpan | None = None) -> tuple[str, str]:
    quote_index = token.find('"')
    if quote_index <= 0:
        raise ReaderSyntaxError(f"invalid tagged literal {token!r}", span=span)
    return token[:quote_index], token[quote_index:]


def _write_cons(value: QyCons) -> str:
    parts: list[str] = []
    current: object = value
    while isinstance(current, QyCons):
        parts.append(write_tuple(cast(TupleForm, current.head)))
        current = current.tail
    if current is QY_EMPTY_LIST:
        return f"({' '.join(parts)})"
    return f"({' '.join(parts)} . {write_tuple(cast(TupleForm, current))})"


def _dot_index(items: tuple[object, ...]) -> int | None:
    for index, item in enumerate(items):
        if isinstance(item, lark.Token) and item.type == "DOT":
            return index
    return None


def _span_from_line_column(line: int | None, column: int | None) -> SourceSpan | None:
    if line is None and column is None:
        return None
    return SourceSpan(None, line, column, line, column)


def _is_surface_quote(form: tuple[Form, ...]) -> bool:
    """Check if a tuple form is ``(quote x)`` — a surface dialect quote."""
    return len(form) == 2 and isinstance(form[0], Symbol) and form[0].name == "quote"


def _is_surface_quasiquote(form: tuple[Form, ...]) -> bool:
    """Check if a tuple form is ``(quasiquote x)`` — a surface dialect quasiquote."""
    return len(form) == 2 and isinstance(form[0], Symbol) and form[0].name == "quasiquote"


def _encode_symbol(name: str) -> str:
    if _can_write_bare(name):
        return name
    return json.dumps(name, ensure_ascii=False)


def _can_write_bare(name: str) -> bool:
    if not name:
        return False
    return not any(char.isspace() or char in """()"';""" for char in name)


def _encode_literal(value: TupleAtom) -> str:
    if isinstance(value, bytes):
        raise TypeError("cannot write Python bytes literal as qy source; use Symbol(...)")
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if value is True:
        return "true"
    if value is False:
        return "false"
    if value is None:
        return "none"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise TypeError(f"cannot write non-finite float literal {value!r} as qy source")
        return repr(value)
    raise TypeError(f"cannot write literal {type(value).__name__} as qy source")
