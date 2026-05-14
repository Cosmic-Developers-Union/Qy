# coding: utf-8
"""Macro hygiene: definition-site alias, rename/capture rewriting."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from typing import Literal
from typing import cast

from qy.evaluator import Environment
from qy.evaluator import EvaluationError as QyResolutionError
from qy.literals import default_literal_type
from qy.macro import CapturedForm
from qy.macro import MacroDefinition
from qy.reader import SpannedTuple
from qy.reader import Symbol

if TYPE_CHECKING:
    from qy.macroexpand import MacroExpansionContext

__all__ = ["MacroRename", "apply_hygiene"]

_HYGIENE_ALIAS_CACHE_KEY = ("qy", "hygiene_alias_namespace")

_SYNTAX_FORM_NAMES = frozenset(
    {
        "all",
        "apply",
        "assert",
        "component",
        "cond",
        "defeffect",
        "define",
        "defun",
        "eval",
        "from",
        "handle",
        "imports",
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


def _tuple_like(original: tuple[object, ...], values: list[object]) -> tuple[object, ...]:
    if isinstance(original, SpannedTuple):
        return SpannedTuple(values, original.span)
    return tuple(values)


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
    if isinstance(value, tuple):
        for item in value:
            _collect_form_ids(item, result)


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
        if isinstance(value, tuple):
            return _tuple_like(
                value,
                [
                    _rewrite_hygienic_form(
                        item,
                        macro,
                        context,
                        call_site_ids,
                        renamed_locals,
                        renames,
                        rename_seen,
                        captured=True,
                    )
                    for item in value
                ],
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
    if not isinstance(value, tuple):
        return value
    if not value:
        return value

    operator = value[0]
    if operator == Symbol("quote"):
        return value
    if operator in {Symbol("quasiquote"), Symbol("unquote"), Symbol("unquote-splicing")}:
        return value
    if operator == Symbol("define"):
        return _rewrite_hygienic_define(
            value,
            macro,
            context,
            call_site_ids,
            renamed_locals,
            renames,
            rename_seen,
        )
    if operator == Symbol("let"):
        return _rewrite_hygienic_let(
            value,
            macro,
            context,
            call_site_ids,
            renamed_locals,
            renames,
            rename_seen,
        )
    if operator == Symbol("lambda"):
        return _rewrite_hygienic_callable(
            value,
            macro,
            context,
            call_site_ids,
            renamed_locals,
            renames,
            rename_seen,
            params_index=1,
            body_start=2,
        )
    if operator in {Symbol("defun"), Symbol("component")}:
        return _rewrite_hygienic_callable(
            value,
            macro,
            context,
            call_site_ids,
            renamed_locals,
            renames,
            rename_seen,
            params_index=2,
            body_start=3,
        )
    if operator == Symbol("handle"):
        return _rewrite_hygienic_handle(
            value,
            macro,
            context,
            call_site_ids,
            renamed_locals,
            renames,
            rename_seen,
        )
    return _tuple_like(
        value,
        [
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
            for item in value
        ],
    )


def _rewrite_hygienic_define(
    form: tuple[object, ...],
    macro: MacroDefinition,
    context: MacroExpansionContext,
    call_site_ids: set[int],
    renamed_locals: dict[str, str],
    renames: list[MacroRename],
    rename_seen: set[tuple[str, str, str]],
) -> tuple[object, ...]:
    if len(form) < 3:
        return form
    body_mapping = dict(renamed_locals)
    rewritten_name = _rewrite_binding_symbol(
        form[1],
        context,
        call_site_ids,
        renames,
        rename_seen,
        body_mapping,
    )
    rewritten_value = _rewrite_hygienic_form(
        form[2],
        macro,
        context,
        call_site_ids,
        body_mapping,
        renames,
        rename_seen,
        captured=False,
    )
    return _tuple_like(form, [form[0], rewritten_name, rewritten_value])


def _rewrite_hygienic_let(
    form: tuple[object, ...],
    macro: MacroDefinition,
    context: MacroExpansionContext,
    call_site_ids: set[int],
    renamed_locals: dict[str, str],
    renames: list[MacroRename],
    rename_seen: set[tuple[str, str, str]],
) -> tuple[object, ...]:
    if len(form) < 2 or not isinstance(form[1], tuple):
        return _tuple_like(
            form,
            [
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
                for item in form
            ],
        )
    bindings_form = form[1]
    body_mapping = dict(renamed_locals)
    rewritten_bindings: list[object] = []
    for binding in bindings_form:
        if not isinstance(binding, tuple) or len(binding) != 2:
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
        name, expr = binding
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
        rewritten_bindings.append(_tuple_like(binding, [rewritten_name, rewritten_expr]))
    rewritten_body = [
        _rewrite_hygienic_form(
            item,
            macro,
            context,
            call_site_ids,
            body_mapping,
            renames,
            rename_seen,
            captured=False,
        )
        for item in form[2:]
    ]
    return _tuple_like(
        form,
        [form[0], _tuple_like(bindings_form, rewritten_bindings), *rewritten_body],
    )


def _rewrite_hygienic_callable(
    form: tuple[object, ...],
    macro: MacroDefinition,
    context: MacroExpansionContext,
    call_site_ids: set[int],
    renamed_locals: dict[str, str],
    renames: list[MacroRename],
    rename_seen: set[tuple[str, str, str]],
    *,
    params_index: int,
    body_start: int,
) -> tuple[object, ...]:
    if len(form) <= params_index or not isinstance(form[params_index], tuple):
        return _tuple_like(
            form,
            [
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
                for item in form
            ],
        )
    params_form = form[params_index]
    assert isinstance(params_form, tuple)
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
        for param in params_form
    ]
    prefix = [
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
        for item in form[:params_index]
    ]
    rewritten_body = [
        _rewrite_hygienic_form(
            item,
            macro,
            context,
            call_site_ids,
            body_mapping,
            renames,
            rename_seen,
            captured=False,
        )
        for item in form[body_start:]
    ]
    return _tuple_like(
        form,
        [*prefix, _tuple_like(params_form, rewritten_params), *rewritten_body],
    )


def _rewrite_hygienic_handle(
    form: tuple[object, ...],
    macro: MacroDefinition,
    context: MacroExpansionContext,
    call_site_ids: set[int],
    renamed_locals: dict[str, str],
    renames: list[MacroRename],
    rename_seen: set[tuple[str, str, str]],
) -> tuple[object, ...]:
    if len(form) != 3 or not isinstance(form[2], tuple):
        return _tuple_like(
            form,
            [
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
                for item in form
            ],
        )
    rewritten_expr = _rewrite_hygienic_form(
        form[1],
        macro,
        context,
        call_site_ids,
        renamed_locals,
        renames,
        rename_seen,
        captured=False,
    )
    handlers_form = form[2]
    rewritten_handlers: list[object] = []
    for clause in handlers_form:
        if not isinstance(clause, tuple) or len(clause) < 3 or not isinstance(clause[1], tuple):
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
        params_form = clause[1]
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
            for param in params_form
        ]
        rewritten_body = [
            _rewrite_hygienic_form(
                item,
                macro,
                context,
                call_site_ids,
                clause_mapping,
                renames,
                rename_seen,
                captured=False,
            )
            for item in clause[2:]
        ]
        rewritten_handlers.append(
            _tuple_like(
                clause, [clause[0], _tuple_like(params_form, rewritten_params), *rewritten_body]
            )
        )
    return _tuple_like(
        form, [form[0], rewritten_expr, _tuple_like(handlers_form, rewritten_handlers)]
    )


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
    context.env.define_hidden(alias, value)
    aliases[key] = alias
    return alias


def _hygiene_alias_namespace(env: Environment) -> dict[tuple[int, str], Symbol]:
    try:
        value = env.cache_lookup(_HYGIENE_ALIAS_CACHE_KEY)
    except KeyError:
        value = env.cache_define(_HYGIENE_ALIAS_CACHE_KEY, {})
    return cast(dict[tuple[int, str], Symbol], value)
