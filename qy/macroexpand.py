# coding: utf-8

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from qy.diagnostics import Diagnostic
from qy.errors import EvaluationError
from qy.errors import QyArityError
from qy.errors import QyTypeError
from qy.evaluator import Environment
from qy.evaluator import MacroDefinition
from qy.evaluator import run_async
from qy.evaluator import standard_environment
from qy.reader import DottedTuple
from qy.reader import Form
from qy.reader import ReaderSyntaxError
from qy.reader import SpannedTuple
from qy.reader import Symbol
from qy.reader import get_span
from qy.reader import read
from qy.values import QyCons
from qy.values import qy_cons_to_tuple

__all__ = [
    "MacroExpansion",
    "macroexpand",
    "macroexpand_async",
    "macroexpand_source",
    "macroexpand_source_async",
]

_MAX_MACRO_EXPANSION_DEPTH = 100


@dataclass(frozen=True, slots=True)
class MacroExpansion:
    forms: list[Form]
    diagnostics: tuple[Diagnostic, ...] = ()

    @property
    def ok(self) -> bool:
        return not any(diagnostic.severity == "error" for diagnostic in self.diagnostics)


def macroexpand(forms: list[Form], env: Environment | None = None) -> MacroExpansion:
    return cast(MacroExpansion, run_async(macroexpand_async(forms, env)))


async def macroexpand_async(
    forms: list[Form],
    env: Environment | None = None,
) -> MacroExpansion:
    runtime_env = env or standard_environment()
    diagnostics: list[Diagnostic] = []
    expanded_forms: list[Form] = []
    for form in forms:
        try:
            expanded_forms.append(
                cast(Form, await _macroexpand_form(form, runtime_env, diagnostics, depth=0))
            )
        except EvaluationError as e:
            diagnostics.append(
                Diagnostic(
                    e.message,
                    line=e.line,
                    column=e.column,
                )
            )
    return MacroExpansion(expanded_forms, tuple(diagnostics))


def macroexpand_source(
    source: str,
    env: Environment | None = None,
    *,
    source_name: str | None = None,
) -> MacroExpansion:
    return cast(
        MacroExpansion,
        run_async(macroexpand_source_async(source, env, source_name=source_name)),
    )


async def macroexpand_source_async(
    source: str,
    env: Environment | None = None,
    *,
    source_name: str | None = None,
) -> MacroExpansion:
    try:
        forms = read(source, source_name=source_name)
    except ReaderSyntaxError as e:
        return MacroExpansion(
            [],
            (Diagnostic(str(e), "error", line=e.line, column=e.column),),
        )
    return await macroexpand_async(forms, env)


async def _macroexpand_form(
    form: object,
    env: Environment,
    diagnostics: list[Diagnostic],
    *,
    depth: int,
) -> object:
    if depth > _MAX_MACRO_EXPANSION_DEPTH:
        raise QyArityError(
            f"macro expansion exceeded {_MAX_MACRO_EXPANSION_DEPTH} nested expansions",
            span=get_span(form),
        )
    if not isinstance(form, tuple) or isinstance(form, DottedTuple) or not form:
        return form

    operator = form[0]
    args = tuple(form[1:])
    if operator == Symbol("quote"):
        return form
    if operator == Symbol("macro"):
        _define_macro(form, env)
        return form

    if isinstance(operator, Symbol):
        try:
            value = env.resolve(operator)
        except EvaluationError:
            value = None
        if isinstance(value, MacroDefinition):
            expanded = await value.expand(args)
            if isinstance(expanded, QyCons):
                expanded = qy_cons_to_tuple(expanded)
            return await _macroexpand_form(expanded, env, diagnostics, depth=depth + 1)

    return _tuple_like(
        form,
        [await _macroexpand_form(item, env, diagnostics, depth=depth) for item in form],
    )


def _define_macro(form: tuple[object, ...], env: Environment) -> None:
    if len(form) < 4:
        raise QyArityError("macro expects a name, parameter list, and body", span=get_span(form))
    _, name, params, *body = form
    if not isinstance(name, Symbol):
        raise QyTypeError(f"macro name must be a symbol, got {name!r}", span=get_span(name))
    if not isinstance(params, tuple):
        raise QyTypeError(
            f"macro parameters must be a list, got {params!r}",
            span=get_span(params),
        )
    param_symbols = []
    for param in params:
        if not isinstance(param, Symbol):
            raise QyTypeError(
                f"macro parameter must be a symbol, got {param!r}",
                span=get_span(param),
            )
        param_symbols.append(param)
    env.define(name, MacroDefinition(name, tuple(param_symbols), tuple(body), env))


def _tuple_like(original: tuple[object, ...], values: list[object]) -> tuple[object, ...]:
    if isinstance(original, SpannedTuple):
        return SpannedTuple(values, original.span)
    return tuple(values)
