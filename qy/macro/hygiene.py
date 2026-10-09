# -*- coding: utf-8 -*-
# Copyright (C) 2025 Cosmic-Developers-Union (CDU), All rights reserved.

"""Macro hygiene: definition-site alias, rename/capture rewriting."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from typing import Literal
from typing import cast

from qy.core.syntax import Symbol
from qy.core.syntax import car
from qy.core.syntax import cdr
from qy.core.syntax import cons
from qy.core.syntax import get_span
from qy.core.syntax import is_chain
from qy.core.syntax import is_nil
from qy.core.syntax import list_to_chain
from qy.errors import EvaluationError as QyResolutionError
from qy.macro import CapturedForm
from qy.macro import MacroDefinition
from qy.session.pre_ss import default_literal_type
from qy.session.runtime_space import RuntimeSpace as Environment

if TYPE_CHECKING:
    from qy.macro.expand import MacroExpansionContext

__all__ = ["MacroRename", "apply_hygiene"]

_HYGIENE_ALIAS_CACHE_KEY = ("qy", "hygiene_alias_namespace")

_SYNTAX_FORM_NAMES = frozenset(
    {
        "all",
        "apply",
        "assert",
        "cond",
        "defeffect",
        "define",
        "defun",
        "eval",
        "from",
        "handle",
        "lambda",
        "let",
        "macro",
        "module",
        "parallel",
        "perform",
        "pipeline",
        "quasiquote",
        "quote",
        "race",
        "resume",
        "unquote",
        "unquote-splicing",
    }
)


@dataclass(frozen=True, slots=True)
class MacroRename:
    original: Symbol
    rewritten: Symbol
    kind: Literal["binding", "definition-site"]


def _chain_items(form: object) -> list[object] | None:
    """把 proper chain 拆成元素列表；非 chain 或 improper chain 返回 None。."""
    if not is_chain(form):
        return None
    items: list[object] = []
    current = form
    while is_chain(current):
        items.append(car(current))
        current = cdr(current)
    if not is_nil(current):
        return None
    return items


def _rebuild(form: object, items: list[object]) -> object:
    """用新元素重建与原 form 同 span 的 chain。."""
    return list_to_chain(items, span=get_span(form))


def _rewrite_default_items(
    items: list[object],
    macro: MacroDefinition,
    context: MacroExpansionContext,
    call_site_ids: set[int],
    renamed_locals: dict[str, str],
    renames: list[MacroRename],
    rename_seen: set[tuple[str, str, str]],
) -> list[object]:
    return [
        _rewrite_hygienic_form(
            item,
            macro,
            context,
            call_site_ids,
            renamed_locals,
            renames,
            rename_seen,
            captured=False,
        )
        for item in items
    ]


def _rewrite_chain_elements(
    value: object,
    macro: MacroDefinition,
    context: MacroExpansionContext,
    call_site_ids: set[int],
    renamed_locals: dict[str, str],
    renames: list[MacroRename],
    rename_seen: set[tuple[str, str, str]],
    *,
    captured: bool = False,
) -> object:
    """逐元素重写 chain（含 improper tail），保留结构与 span。."""
    span = get_span(value)
    elements: list[object] = []
    current = value
    while is_chain(current):
        elements.append(
            _rewrite_hygienic_form(
                car(current),
                macro,
                context,
                call_site_ids,
                renamed_locals,
                renames,
                rename_seen,
                captured=captured,
            )
        )
        current = cdr(current)
    if is_nil(current):
        return list_to_chain(elements, span=span)
    result = _rewrite_hygienic_form(
        current,
        macro,
        context,
        call_site_ids,
        renamed_locals,
        renames,
        rename_seen,
        captured=captured,
    )
    for item in reversed(elements):
        result = cons(item, result, span=span)
    return result


def apply_hygiene(
    value: object,
    macro: MacroDefinition,
    args: tuple[object, ...],
    context: MacroExpansionContext,
) -> tuple[object, tuple[MacroRename, ...]]:
    call_site_ids: set[int] = set()
    for arg in args:
        _collect_form_ids(arg, call_site_ids)
    renames: list[MacroRename] = []
    rename_seen: set[tuple[str, str, str]] = set()
    rewritten = _rewrite_hygienic_form(
        value,
        macro,
        context,
        call_site_ids,
        {},
        renames,
        rename_seen,
        captured=False,
    )
    return rewritten, tuple(renames)


def _collect_form_ids(value: object, result: set[int]) -> None:
    result.add(id(value))
    if isinstance(value, CapturedForm):
        _collect_form_ids(value.value, result)
        return
    if is_chain(value):
        current: object = value
        while is_chain(current):
            _collect_form_ids(car(current), result)
            current = cdr(current)


def _rewrite_hygienic_form(
    value: object,
    macro: MacroDefinition,
    context: MacroExpansionContext,
    call_site_ids: set[int],
    renamed_locals: dict[str, str],
    renames: list[MacroRename],
    rename_seen: set[tuple[str, str, str]],
    *,
    captured: bool,
) -> object:
    if isinstance(value, CapturedForm):
        return _rewrite_hygienic_form(
            value.value,
            macro,
            context,
            call_site_ids,
            renamed_locals,
            renames,
            rename_seen,
            captured=True,
        )
    if captured or id(value) in call_site_ids:
        if is_chain(value):
            return _rewrite_chain_elements(
                value,
                macro,
                context,
                call_site_ids,
                renamed_locals,
                renames,
                rename_seen,
                captured=True,
            )
        return value
    if isinstance(value, Symbol):
        if value.name in renamed_locals:
            return Symbol(renamed_locals[value.name], value.span)
        if context.resolve_macro(value) is not None:
            return value
        alias = _definition_site_alias(value, macro, context)
        if alias is None:
            return value
        _record_macro_rename(
            renames,
            rename_seen,
            value,
            alias,
            "definition-site",
        )
        return Symbol(alias.name, value.span)

    # Handle Chain forms
    if is_chain(value):
        if is_nil(value):
            return value
        operator = car(value)

        # Special forms that should not be rewritten
        if operator == Symbol("quote"):
            return value
        if operator in {Symbol("quasiquote"), Symbol("unquote"), Symbol("unquote-splicing")}:
            return value

        items = _chain_items(value)
        if items is None:
            # improper chain：逐元素重写，保留 dotted tail
            return _rewrite_chain_elements(
                value,
                macro,
                context,
                call_site_ids,
                renamed_locals,
                renames,
                rename_seen,
            )

        # Handle special forms that need custom rewriting
        if operator == Symbol("define") and len(items) >= 3:
            return _rebuild(
                value,
                _rewrite_hygienic_define(
                    items,
                    macro,
                    context,
                    call_site_ids,
                    renamed_locals,
                    renames,
                    rename_seen,
                ),
            )

        if operator == Symbol("let") and len(items) >= 2:
            return _rebuild(
                value,
                _rewrite_hygienic_let(
                    items,
                    macro,
                    context,
                    call_site_ids,
                    renamed_locals,
                    renames,
                    rename_seen,
                ),
            )

        if operator == Symbol("lambda") and len(items) >= 2:
            return _rebuild(
                value,
                _rewrite_hygienic_callable(
                    items,
                    macro,
                    context,
                    call_site_ids,
                    renamed_locals,
                    renames,
                    rename_seen,
                    params_index=1,
                    body_start=2,
                ),
            )

        if operator == Symbol("defun") and len(items) >= 3:
            return _rebuild(
                value,
                _rewrite_hygienic_callable(
                    items,
                    macro,
                    context,
                    call_site_ids,
                    renamed_locals,
                    renames,
                    rename_seen,
                    params_index=2,
                    body_start=3,
                ),
            )

        if operator == Symbol("handle") and len(items) == 3:
            return _rebuild(
                value,
                _rewrite_hygienic_handle(
                    items,
                    macro,
                    context,
                    call_site_ids,
                    renamed_locals,
                    renames,
                    rename_seen,
                ),
            )

        # Default: rewrite all items
        return _rebuild(
            value,
            _rewrite_default_items(
                items,
                macro,
                context,
                call_site_ids,
                renamed_locals,
                renames,
                rename_seen,
            ),
        )

    return value


def _rewrite_hygienic_define(
    items: list[object],
    macro: MacroDefinition,
    context: MacroExpansionContext,
    call_site_ids: set[int],
    renamed_locals: dict[str, str],
    renames: list[MacroRename],
    rename_seen: set[tuple[str, str, str]],
) -> list[object]:
    if len(items) < 3:
        return items
    body_mapping = dict(renamed_locals)
    rewritten_name = _rewrite_binding_symbol(
        items[1],
        context,
        call_site_ids,
        renames,
        rename_seen,
        body_mapping,
    )
    rewritten_value = _rewrite_hygienic_form(
        items[2],
        macro,
        context,
        call_site_ids,
        body_mapping,
        renames,
        rename_seen,
        captured=False,
    )
    return [items[0], rewritten_name, rewritten_value]


def _rewrite_hygienic_let(
    items: list[object],
    macro: MacroDefinition,
    context: MacroExpansionContext,
    call_site_ids: set[int],
    renamed_locals: dict[str, str],
    renames: list[MacroRename],
    rename_seen: set[tuple[str, str, str]],
) -> list[object]:
    if len(items) < 2:
        return _rewrite_default_items(
            items, macro, context, call_site_ids, renamed_locals, renames, rename_seen
        )
    bindings_form = items[1]
    bindings_items = _chain_items(bindings_form)
    if bindings_items is None:
        return _rewrite_default_items(
            items, macro, context, call_site_ids, renamed_locals, renames, rename_seen
        )
    body_mapping = dict(renamed_locals)
    rewritten_bindings: list[object] = []
    for binding in bindings_items:
        binding_items = _chain_items(binding)
        if binding_items is None or len(binding_items) != 2:
            rewritten_bindings.append(
                _rewrite_hygienic_form(
                    binding,
                    macro,
                    context,
                    call_site_ids,
                    body_mapping,
                    renames,
                    rename_seen,
                    captured=False,
                )
            )
            continue
        name, expr = binding_items
        rewritten_expr = _rewrite_hygienic_form(
            expr,
            macro,
            context,
            call_site_ids,
            body_mapping,
            renames,
            rename_seen,
            captured=False,
        )
        rewritten_name = _rewrite_binding_symbol(
            name,
            context,
            call_site_ids,
            renames,
            rename_seen,
            body_mapping,
        )
        rewritten_bindings.append(_rebuild(binding, [rewritten_name, rewritten_expr]))
    rewritten_body = _rewrite_default_items(
        items[2:], macro, context, call_site_ids, body_mapping, renames, rename_seen
    )
    return [items[0], _rebuild(bindings_form, rewritten_bindings), *rewritten_body]


def _rewrite_hygienic_callable(
    items: list[object],
    macro: MacroDefinition,
    context: MacroExpansionContext,
    call_site_ids: set[int],
    renamed_locals: dict[str, str],
    renames: list[MacroRename],
    rename_seen: set[tuple[str, str, str]],
    *,
    params_index: int,
    body_start: int,
) -> list[object]:
    params_form = items[params_index] if len(items) > params_index else None
    params_items = _chain_items(params_form)
    if params_items is None:
        return _rewrite_default_items(
            items, macro, context, call_site_ids, renamed_locals, renames, rename_seen
        )
    body_mapping = dict(renamed_locals)
    rewritten_params = [
        _rewrite_binding_symbol(
            param,
            context,
            call_site_ids,
            renames,
            rename_seen,
            body_mapping,
        )
        for param in params_items
    ]
    prefix = _rewrite_default_items(
        items[:params_index], macro, context, call_site_ids, renamed_locals, renames, rename_seen
    )
    rewritten_body = _rewrite_default_items(
        items[body_start:], macro, context, call_site_ids, body_mapping, renames, rename_seen
    )
    return [*prefix, _rebuild(params_form, rewritten_params), *rewritten_body]


def _rewrite_hygienic_handle(
    items: list[object],
    macro: MacroDefinition,
    context: MacroExpansionContext,
    call_site_ids: set[int],
    renamed_locals: dict[str, str],
    renames: list[MacroRename],
    rename_seen: set[tuple[str, str, str]],
) -> list[object]:
    if len(items) != 3:
        return _rewrite_default_items(
            items, macro, context, call_site_ids, renamed_locals, renames, rename_seen
        )
    handlers_form = items[2]
    handlers_items = _chain_items(handlers_form)
    if handlers_items is None:
        return _rewrite_default_items(
            items, macro, context, call_site_ids, renamed_locals, renames, rename_seen
        )
    rewritten_expr = _rewrite_hygienic_form(
        items[1],
        macro,
        context,
        call_site_ids,
        renamed_locals,
        renames,
        rename_seen,
        captured=False,
    )
    rewritten_handlers: list[object] = []
    for clause in handlers_items:
        clause_items = _chain_items(clause)
        if clause_items is None or len(clause_items) < 3:
            rewritten_handlers.append(
                _rewrite_hygienic_form(
                    clause,
                    macro,
                    context,
                    call_site_ids,
                    renamed_locals,
                    renames,
                    rename_seen,
                    captured=False,
                )
            )
            continue
        params_form = clause_items[1]
        params_items = _chain_items(params_form)
        if params_items is None:
            rewritten_handlers.append(
                _rewrite_hygienic_form(
                    clause,
                    macro,
                    context,
                    call_site_ids,
                    renamed_locals,
                    renames,
                    rename_seen,
                    captured=False,
                )
            )
            continue
        clause_mapping = dict(renamed_locals)
        rewritten_params = [
            _rewrite_binding_symbol(
                param,
                context,
                call_site_ids,
                renames,
                rename_seen,
                clause_mapping,
            )
            for param in params_items
        ]
        rewritten_body = _rewrite_default_items(
            clause_items[2:],
            macro,
            context,
            call_site_ids,
            clause_mapping,
            renames,
            rename_seen,
        )
        rewritten_handlers.append(
            _rebuild(
                clause,
                [clause_items[0], _rebuild(params_form, rewritten_params), *rewritten_body],
            )
        )
    return [items[0], rewritten_expr, _rebuild(handlers_form, rewritten_handlers)]


def _rewrite_binding_symbol(
    value: object,
    context: MacroExpansionContext,
    call_site_ids: set[int],
    renames: list[MacroRename],
    rename_seen: set[tuple[str, str, str]],
    renamed_locals: dict[str, str],
) -> object:
    if not isinstance(value, Symbol) or id(value) in call_site_ids:
        return value
    rewritten = context.fresh_hygienic_symbol(value.name, category="binding")
    rewritten = Symbol(rewritten.name, value.span)
    renamed_locals[value.name] = rewritten.name
    _record_macro_rename(renames, rename_seen, value, rewritten, "binding")
    return rewritten


def _record_macro_rename(
    renames: list[MacroRename],
    rename_seen: set[tuple[str, str, str]],
    original: Symbol,
    rewritten: Symbol,
    kind: Literal["binding", "definition-site"],
) -> None:
    key = (kind, original.name, rewritten.name)
    if key in rename_seen:
        return
    rename_seen.add(key)
    renames.append(MacroRename(original, rewritten, kind))


def _definition_site_alias(
    symbol: Symbol,
    macro: MacroDefinition,
    context: MacroExpansionContext,
) -> Symbol | None:
    if symbol.name in _SYNTAX_FORM_NAMES:
        return None
    if default_literal_type(symbol) is not None:
        return None
    try:
        value = macro.closure.resolve(symbol)
    except QyResolutionError:
        return None
    aliases = _hygiene_alias_namespace(context.env)
    key = (id(macro), symbol.name)
    if key in aliases:
        return aliases[key]
    alias = context.fresh_hygienic_symbol(symbol.name, category="def")
    # 装到 chain 根部：module body 的临时子 env 里创建的别名，HIR lowering 也要能解析。
    context.env.define_hidden_root(alias, value)
    aliases[key] = alias
    return alias


def _hygiene_alias_namespace(env: Environment) -> dict[tuple[int, str], Symbol]:
    try:
        value = env.cache_lookup(_HYGIENE_ALIAS_CACHE_KEY)
    except KeyError:
        value = env.cache_define(_HYGIENE_ALIAS_CACHE_KEY, {})
    return cast(dict[tuple[int, str], Symbol], value)
