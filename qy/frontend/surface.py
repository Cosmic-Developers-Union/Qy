# coding: utf-8
"""Surface dialect 实现。.

执行 default surface dialect 的 sugar rewrite：
- 'x -> (quote x)
- `x -> (quasiquote x)
- ,x -> (unquote x)
- ,@x -> (unquote-splicing x)

这是纯静态的 spelling rewrite，不执行 runtime evaluation。

禁止：
- 不得实现 unrestricted reader macro。
- 不得引入 runtime evaluation。
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import cast

from qy.core.syntax import Chain
from qy.core.syntax import car
from qy.core.syntax import cdr
from qy.core.syntax import cons
from qy.core.syntax import is_chain
from qy.core.syntax import is_nil
from qy.core.syntax import list_to_chain
from qy.frontend.form import DottedTuple
from qy.frontend.form import Form
from qy.frontend.form import SpannedTuple
from qy.frontend.form import Symbol
from qy.frontend.form import get_span
from qy.source.span import SourceSpan

__all__ = ["expand_surface_dialect"]


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


def _expand_surface_program(forms: list[Form]) -> list[Form]:
    return cast(list[Form], list(_expand_surface_sequence(tuple(forms), in_quasiquote=False)))


def _expand_surface_form(form: object, *, in_quasiquote: bool) -> object:
    if isinstance(form, Symbol):
        expanded = _expand_surface_symbol(form, in_quasiquote=in_quasiquote)
        if expanded is not form:
            return expanded
        return form
    if isinstance(form, Chain):
        return _expand_surface_chain(form, in_quasiquote=in_quasiquote)
    if isinstance(form, DottedTuple):
        return _expand_surface_dotted_tuple(form, in_quasiquote=in_quasiquote)
    if isinstance(form, tuple):
        return _expand_surface_tuple(form, in_quasiquote=in_quasiquote)
    return form


def _expand_surface_sequence(
    forms: tuple[object, ...], *, in_quasiquote: bool
) -> tuple[object, ...]:
    expanded: list[object] = []
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
        if (
            isinstance(form, Symbol)
            and form.name == "`"
            and index + 1 < len(forms)
            and _forms_are_adjacent(form, forms[index + 1])
        ):
            expanded.append(
                _surface_call(
                    "quasiquote",
                    (_expand_surface_form(forms[index + 1], in_quasiquote=True),),
                    span=_combine_spans(form, forms[index + 1]),
                )
            )
            index += 2
            continue
        expanded.append(_expand_surface_form(form, in_quasiquote=in_quasiquote))
        index += 1
    return tuple(expanded)


def _expand_chain_sequence(chain: object, *, in_quasiquote: bool) -> object:
    if is_nil(chain):
        return chain

    span = get_span(chain)
    expanded: list[object] = []
    current = chain

    while is_chain(current):
        head = car(current)
        tail = cdr(current)

        if (
            isinstance(head, Symbol)
            and head.name == "'"
            and is_chain(tail)
            and _forms_are_adjacent(head, car(tail))
        ):
            quoted_form = car(tail)
            expanded.append(
                _surface_call(
                    "quote",
                    (_expand_surface_form(quoted_form, in_quasiquote=in_quasiquote),),
                    span=_combine_spans(head, quoted_form),
                )
            )
            current = cdr(tail)
            continue

        if (
            isinstance(head, Symbol)
            and head.name == "`"
            and is_chain(tail)
            and _forms_are_adjacent(head, car(tail))
        ):
            quasiquoted_form = car(tail)
            expanded.append(
                _surface_call(
                    "quasiquote",
                    (_expand_surface_form(quasiquoted_form, in_quasiquote=True),),
                    span=_combine_spans(head, quasiquoted_form),
                )
            )
            current = cdr(tail)
            continue

        expanded.append(_expand_surface_form(head, in_quasiquote=in_quasiquote))
        current = tail

    if not is_nil(current):
        result = _expand_surface_form(current, in_quasiquote=in_quasiquote)
        for item in reversed(expanded):
            result = cons(item, result, span=span)
        return result

    return list_to_chain(expanded, span=span)


def _expand_surface_chain(chain: Chain, *, in_quasiquote: bool) -> object:
    if is_nil(chain):
        return chain

    get_span(chain)

    if not is_chain(chain):
        return chain

    head = car(chain)

    if not isinstance(head, Symbol):
        return _expand_chain_sequence(chain, in_quasiquote=in_quasiquote)

    if in_quasiquote:
        if head.name == "unquote" or head.name == "unquote-splicing":
            return _expand_chain_sequence(chain, in_quasiquote=False)
        if head.name == "quasiquote":
            return _expand_quasiquote_surface_chain(chain, in_quasiquote=in_quasiquote)
        return _expand_chain_sequence(chain, in_quasiquote=in_quasiquote)

    match head.name:
        case "define":
            return _expand_define_surface_chain(chain, in_quasiquote=in_quasiquote)
        case "defun" | "macro":
            return _expand_named_body_surface_chain(chain, in_quasiquote=in_quasiquote)
        case "lambda":
            return _expand_lambda_surface_chain(chain, in_quasiquote=in_quasiquote)
        case "let":
            return _expand_let_surface_chain(chain, in_quasiquote=in_quasiquote)
        case "defeffect" | "exports" | "from" | "import":
            return chain
        case "module":
            return _expand_module_surface_chain(chain, in_quasiquote=in_quasiquote)
        case "quasiquote":
            return _expand_quasiquote_surface_chain(chain, in_quasiquote=in_quasiquote)

    return _expand_chain_sequence(chain, in_quasiquote=in_quasiquote)


def _chain_to_list_safe(chain: object) -> tuple[list[object], object]:
    items = []
    current = chain
    while is_chain(current):
        items.append(car(current))
        current = cdr(current)
    return items, current


def _expand_define_surface_chain(chain: Chain, *, in_quasiquote: bool) -> object:
    items, tail = _chain_to_list_safe(chain)
    if not is_nil(tail):
        return chain
    if len(items) <= 2:
        return chain
    span = get_span(chain)
    expanded_name = (
        _expand_surface_form(items[1], in_quasiquote=in_quasiquote) if in_quasiquote else items[1]
    )
    expanded_values = _expand_surface_sequence(tuple(items[2:]), in_quasiquote=in_quasiquote)
    return list_to_chain([items[0], expanded_name, *list(expanded_values)], span=span)


def _expand_named_body_surface_chain(chain: Chain, *, in_quasiquote: bool) -> object:
    items, tail = _chain_to_list_safe(chain)
    if not is_nil(tail):
        return chain
    if len(items) <= 3:
        return chain
    span = get_span(chain)
    expanded_body = _expand_surface_sequence(tuple(items[3:]), in_quasiquote=in_quasiquote)
    return list_to_chain([items[0], items[1], items[2], *list(expanded_body)], span=span)


def _expand_lambda_surface_chain(chain: Chain, *, in_quasiquote: bool) -> object:
    items, tail = _chain_to_list_safe(chain)
    if not is_nil(tail):
        return chain
    if len(items) <= 2:
        return chain
    span = get_span(chain)
    expanded_args = (
        _expand_surface_form(items[1], in_quasiquote=in_quasiquote) if in_quasiquote else items[1]
    )
    expanded_body = _expand_surface_sequence(tuple(items[2:]), in_quasiquote=in_quasiquote)
    return list_to_chain([items[0], expanded_args, *list(expanded_body)], span=span)


def _expand_module_surface_chain(chain: Chain, *, in_quasiquote: bool) -> object:
    items, tail = _chain_to_list_safe(chain)
    if not is_nil(tail):
        return chain
    if len(items) <= 2:
        return chain
    span = get_span(chain)
    expanded_body = _expand_surface_sequence(tuple(items[2:]), in_quasiquote=in_quasiquote)
    return list_to_chain([items[0], items[1], *list(expanded_body)], span=span)


def _expand_quasiquote_surface_chain(chain: Chain, *, in_quasiquote: bool) -> object:
    items, tail = _chain_to_list_safe(chain)
    if not is_nil(tail):
        return chain
    if len(items) != 2:
        expanded_items = [_expand_surface_form(item, in_quasiquote=in_quasiquote) for item in items]
        return list_to_chain(expanded_items, span=get_span(chain))
    span = get_span(chain)
    return list_to_chain(
        [items[0], _expand_surface_form(items[1], in_quasiquote=True)],
        span=span,
    )


def _expand_let_surface_chain(chain: Chain, *, in_quasiquote: bool) -> object:
    items, tail = _chain_to_list_safe(chain)
    if not is_nil(tail):
        return chain
    if len(items) <= 2:
        return chain
    span = get_span(chain)

    bindings = items[1]
    if is_chain(bindings):
        expanded_bindings = []
        binding_items, binding_tail = _chain_to_list_safe(bindings)
        if not is_nil(binding_tail):
            pass
        else:
            for binding in binding_items:
                if is_chain(binding):
                    b_items, b_tail = _chain_to_list_safe(binding)
                    if is_nil(b_tail) and len(b_items) > 1:
                        values_chain = list_to_chain(b_items[1:])
                        expanded_values_chain = _expand_chain_sequence(
                            values_chain, in_quasiquote=in_quasiquote
                        )
                        expanded_values = (
                            list(cast(Iterable[object], expanded_values_chain))
                            if is_chain(expanded_values_chain)
                            else [expanded_values_chain]
                        )
                        expanded_bindings.append(
                            list_to_chain([b_items[0], *expanded_values], span=get_span(binding))
                        )
                    else:
                        expanded_bindings.append(binding)
                else:
                    expanded_bindings.append(binding)
            bindings = list_to_chain(expanded_bindings, span=get_span(bindings))

    expanded_body = _expand_surface_sequence(tuple(items[2:]), in_quasiquote=in_quasiquote)
    return list_to_chain([items[0], bindings, *list(expanded_body)], span=span)


def _expand_surface_tuple(form: tuple[object, ...], *, in_quasiquote: bool) -> Form:
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


def _expand_define_surface(form: tuple[object, ...], *, in_quasiquote: bool) -> Form:
    if len(form) <= 2:
        return SpannedTuple(form, get_span(form))
    values = _expand_surface_sequence(tuple(form[2:]), in_quasiquote=in_quasiquote)
    return SpannedTuple((form[0], form[1], *values), get_span(form))


def _expand_named_body_surface(form: tuple[object, ...], *, in_quasiquote: bool) -> Form:
    if len(form) <= 3:
        return SpannedTuple(form, get_span(form))
    body = _expand_surface_sequence(tuple(form[3:]), in_quasiquote=in_quasiquote)
    return SpannedTuple((form[0], form[1], form[2], *body), get_span(form))


def _expand_lambda_surface(form: tuple[object, ...], *, in_quasiquote: bool) -> Form:
    if len(form) <= 2:
        return SpannedTuple(form, get_span(form))
    body = _expand_surface_sequence(tuple(form[2:]), in_quasiquote=in_quasiquote)
    return SpannedTuple((form[0], form[1], *body), get_span(form))


def _expand_let_surface(form: tuple[object, ...], *, in_quasiquote: bool) -> Form:
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


def _expand_let_binding_surface(binding: tuple[object, ...], *, in_quasiquote: bool) -> Form:
    if len(binding) <= 1:
        return SpannedTuple(binding, get_span(binding))
    values = _expand_surface_sequence(tuple(binding[1:]), in_quasiquote=in_quasiquote)
    return SpannedTuple((binding[0], *values), get_span(binding))


def _expand_surface_symbol(symbol: Symbol, *, in_quasiquote: bool) -> object:
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


def _surface_call(name: str, args: tuple[object, ...], *, span: SourceSpan | None) -> object:
    return list_to_chain([Symbol(name, span), *args], span=span)


def _forms_are_adjacent(left: object, right: object) -> bool:
    left_span = get_span(left)
    right_span = get_span(right)

    if is_nil(right) and right_span is None and left_span is not None:
        return True

    return (
        left_span is not None
        and right_span is not None
        and left_span.source == right_span.source
        and left_span.end_line == right_span.start_line
        and left_span.end_column == right_span.start_column
    )


def _combine_spans(left: object, right: object) -> SourceSpan | None:
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
