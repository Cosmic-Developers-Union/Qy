# coding: utf-8
"""Qy 前端 Reader 实现。.

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
from typing import TYPE_CHECKING
from typing import cast

import lark

from qy.core.syntax import Chain
from qy.core.syntax import car
from qy.core.syntax import cdr
from qy.core.syntax import cons
from qy.core.syntax import is_chain
from qy.core.syntax import is_nil
from qy.core.syntax import list_to_chain
from qy.core.syntax import nil
from qy.errors import QySyntaxError
from qy.frontend.form import DottedTuple
from qy.frontend.form import Form
from qy.frontend.form import SpannedTuple
from qy.frontend.form import Symbol
from qy.frontend.form import TupleAtom
from qy.frontend.form import TupleForm
from qy.frontend.form import chain_to_spanned_tuple
from qy.frontend.form import get_span
from qy.frontend.form import spanned_tuple_to_chain
from qy.source.span import SourceSpan

if TYPE_CHECKING:
    from qy.frontend.cst import CstProgram
    from qy.frontend.reader_macros import ReaderMacroRegistry

__all__ = [
    "GRAMMAR",
    "Chain",
    "DottedTuple",
    "Form",
    "ReaderSyntaxError",
    "SourceSpan",
    "SpannedTuple",
    "Symbol",
    "TupleForm",
    "_decode_string_symbol",
    "_is_string_symbol",
    "car",
    "cdr",
    "chain_to_spanned_tuple",
    "cons",
    "expand_surface_dialect",
    "form_to_tuple",
    "get_span",
    "is_chain",
    "is_nil",
    "list_to_chain",
    "nil",
    "parse_cst",
    "read",
    "read_cst",
    "read_one",
    "read_one_tuple",
    "read_raw",
    "read_tuple",
    "spanned_tuple_to_chain",
    "tuple_to_form",
    "write",
    "write_program",
    "write_tuple",
    "write_tuple_program",
]


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

    def list_expr(self, meta: lark.tree.Meta, *items: object) -> object:
        span = self._span(meta)
        dot_index = _dot_index(items)
        if dot_index is None:
            # Proper list: 转换为 Chain
            return list_to_chain(items, tail=nil, span=span)
        if dot_index == 0:
            raise ReaderSyntaxError("dotted pair must have a head before .", span=span)
        if dot_index != len(items) - 2:
            raise ReaderSyntaxError("dotted pair must have exactly one tail after .", span=span)
        # Improper list: 从后向前构造
        heads = items[:dot_index]
        tail_form = items[dot_index + 1]
        result = tail_form
        for head in reversed(heads):
            result = cons(head, result, span=span)
        return result

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

    def tagged_quoted_symbol(self, meta: lark.tree.Meta, token: lark.Token) -> object:
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

    def tagged_multiline_symbol(self, meta: lark.tree.Meta, token: lark.Token) -> object:
        del meta
        return self._tagged_literal(token)

    def _tagged_literal(self, token: lark.Token) -> object:
        span = self._token_span(token)
        tag, literal = _split_tagged_literal(str(token), span)
        # 构造 (tag (quote literal))
        quote_form = list_to_chain(
            [Symbol("quote", span), Symbol(literal, span)],
            span=span,
        )
        return list_to_chain(
            [Symbol(tag, span), quote_form],
            span=span,
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
    from qy.frontend.surface import expand_surface_dialect as _impl

    return _impl(forms)


def read(source: str, *, source_name: str | None = None) -> list[Form]:
    return expand_surface_dialect(read_raw(source, source_name=source_name))


def read_one(source: str, *, source_name: str | None = None) -> Form:
    forms = read(source, source_name=source_name)
    if len(forms) != 1:
        raise ReaderSyntaxError(f"expected exactly one form, got {len(forms)}")
    return forms[0]


def read_tuple(source: str) -> list[TupleForm]:
    return [form_to_tuple(form) for form in read(source)]


def read_one_tuple(source: str) -> TupleForm:
    return form_to_tuple(read_one(source))


def form_to_tuple(form: object) -> TupleForm:
    if isinstance(form, Symbol):
        if _is_string_symbol(form.name):
            return _decode_string_symbol(form)
        return form
    if isinstance(form, Chain):
        # 转换 Chain 到 tuple
        items = []
        current = form
        while is_chain(current):
            items.append(form_to_tuple(car(current)))
            current = cdr(current)
        # 处理 improper list
        if not is_nil(current):
            return (*items, Symbol("."), form_to_tuple(current))
        return tuple(items)
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


def write(form: object) -> str:
    if isinstance(form, Symbol):
        if _is_string_symbol(form.name):
            return form.name
        return _encode_symbol(form.name)
    if isinstance(form, Chain):
        # 处理 Chain
        items = []
        current = form
        while is_chain(current):
            items.append(write(car(current)))
            current = cdr(current)
        # 处理 improper list
        if not is_nil(current):
            return f"({' '.join(items)} . {write(current)})"
        # 处理 surface quote
        if len(items) == 2 and items[0] == "quote":
            return "'" + items[1]
        if len(items) == 2 and items[0] == "quasiquote":
            return "`" + items[1]
        return f"({' '.join(items)})"
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
    from qy.sem.core import T

    if form is nil:
        return "nil"
    if form is T:
        return "T"
    if isinstance(form, Chain):
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


def _write_cons(value: Chain) -> str:
    parts: list[str] = []
    current: object = value
    while isinstance(current, Chain):
        parts.append(write_tuple(cast(TupleForm, current.head)))
        current = current.tail
    if current is nil:
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


def _is_surface_quote(form: tuple[object, ...]) -> bool:
    """Check if a tuple form is ``(quote x)`` — a surface dialect quote."""
    return len(form) == 2 and isinstance(form[0], Symbol) and form[0].name == "quote"


def _is_surface_quasiquote(form: tuple[object, ...]) -> bool:
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


# ============================================================================
# CST path: Source → CstProgram → list[Form]
# ============================================================================


def parse_cst(source: str, *, source_name: str | None = None) -> CstProgram:
    """Parse source into a CST (trivia-preserving)."""
    from qy.frontend.cst_parser import parse_cst as _parse_cst

    return _parse_cst(source, source_name=source_name)


def read_cst(
    cst: CstProgram,
    *,
    registry: ReaderMacroRegistry | None = None,
) -> list[Form]:
    """Convert a CstProgram into a list of Forms (raw AST).

    Applies reader macros for tagged atoms if a registry is provided.
    Unregistered tags use the default behavior: tag"lit" → (tag (quote "lit")).
    """
    from qy.frontend.cst import AtomKind
    from qy.frontend.cst import CstAtom
    from qy.frontend.cst import CstList

    if registry is None:
        from qy.frontend.reader_macros import default_registry

        registry = default_registry()

    def _convert_node(node: CstAtom | CstList) -> Form:
        if isinstance(node, CstAtom):
            return _convert_atom(node)
        return _convert_list(node)

    def _convert_atom(atom: CstAtom) -> Form:
        span = atom.span
        text = atom.text
        match atom.kind:
            case AtomKind.BARE:
                return Symbol(text, span)
            case AtomKind.QUOTED:
                return Symbol(text, span)
            case AtomKind.RAW_QUOTED:
                return Symbol(text, span)
            case AtomKind.MULTILINE:
                return Symbol(text, span)
            case AtomKind.RAW_MULTILINE:
                return Symbol(text, span)
            case AtomKind.TAGGED_QUOTED | AtomKind.TAGGED_MULTILINE:
                tag, literal = _split_tagged_literal(text, span)
                entry = registry.lookup(tag)
                if entry is not None:
                    return entry.handler(atom)
                # Default: (tag (quote literal))
                quote_form = list_to_chain(
                    [Symbol("quote", span), Symbol(literal, span)],
                    span=span,
                )
                return cast(
                    Form,
                    list_to_chain(
                        [Symbol(tag, span), quote_form],
                        span=span,
                    ),
                )
            case _:  # pragma: no cover
                return Symbol(text, span)

    def _convert_list(lst: CstList) -> Form:
        span = lst.span
        if lst.tail is not None:
            # Dotted pair: build improper list
            heads = [
                _convert_node(child)
                for child in lst.children
                if isinstance(child, (CstAtom, CstList))
            ]
            tail_form = _convert_node(lst.tail) if isinstance(lst.tail, (CstAtom, CstList)) else nil
            result: object = tail_form
            for head in reversed(heads):
                result = cons(head, result, span=span)
            return cast(Form, result)
        # Proper list
        items = [
            _convert_node(child) for child in lst.children if isinstance(child, (CstAtom, CstList))
        ]
        return cast(Form, list_to_chain(items, span=span))

    forms: list[Form] = []
    for node in cst.children:
        if isinstance(node, (CstAtom, CstList)):
            forms.append(_convert_node(node))
    return forms


# ============================================================================
# 兼容层函数（迁移期使用）
# ============================================================================
