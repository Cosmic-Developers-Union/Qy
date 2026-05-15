# coding: utf-8

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from typing import Literal
from typing import cast

from qy.async_runtime import run_async
from qy.compile_time import compile_time_binding_names
from qy.compile_time import compile_time_environment
from qy.diagnostics import Diagnostic
from qy.environment import Environment
from qy.environment import standard_environment
from qy.errors import EvaluationError
from qy.errors import QyArityError
from qy.errors import QyEffectSignal
from qy.errors import QyRuntimeError
from qy.errors import QyTypeError
from qy.macro import CapturedForm
from qy.macro import MacroDefinition
from qy.macro import MacroExpansionServices
from qy.macro_hygiene import MacroRename
from qy.macro_hygiene import _tuple_like
from qy.macro_hygiene import apply_hygiene
from qy.macro_scope import MacroScope
from qy.macro_trace import MacroExpansionTrace
from qy.macro_trace import MacroSourceMapEntry
from qy.reader import DottedTuple
from qy.reader import Form
from qy.reader import ReaderSyntaxError
from qy.reader import Symbol
from qy.reader import get_span
from qy.reader import read
from qy.stdlib import load_module
from qy.stdlib.imports import parse_from_import
from qy.values import QyCons
from qy.values import qy_cons_to_tuple

__all__ = [
    "MacroEffectPolicy",
    "MacroExpansion",
    "MacroExpansionOptions",
    "MacroExpansionTrace",
    "MacroRename",
    "MacroSourceMapEntry",
    "macroexpand",
    "macroexpand_async",
    "macroexpand_source",
    "macroexpand_source_async",
]

MacroEffectPolicy = Literal["deny", "allow"]
_MAX_MACRO_EXPANSION_DEPTH = 100
_MACRO_NAMESPACE_CACHE_KEY = ("qy", "macro_namespace")
_MODULE_MACRO_NAMESPACE_CACHE_KEY = ("qy", "module_macro_namespace")


@dataclass(frozen=True, slots=True)
class MacroExpansionOptions:
    max_depth: int = _MAX_MACRO_EXPANSION_DEPTH
    effect_policy: MacroEffectPolicy = "deny"


@dataclass(frozen=True, slots=True)
class MacroExpansion:
    forms: list[Form]
    diagnostics: tuple[Diagnostic, ...] = ()
    traces: tuple[MacroExpansionTrace, ...] = ()

    @property
    def ok(self) -> bool:
        return not any(diagnostic.severity == "error" for diagnostic in self.diagnostics)

    @property
    def source_map(self) -> tuple[MacroSourceMapEntry, ...]:
        return tuple(trace.source_map_entry() for trace in self.traces)


def macroexpand(
    forms: list[Form],
    env: Environment | None = None,
    *,
    options: MacroExpansionOptions | None = None,
) -> MacroExpansion:
    return cast(MacroExpansion, run_async(macroexpand_async(forms, env, options=options)))


async def macroexpand_async(
    forms: list[Form],
    env: Environment | None = None,
    *,
    options: MacroExpansionOptions | None = None,
) -> MacroExpansion:
    runtime_env = env or standard_environment()
    context = MacroExpansionContext.create(runtime_env, options or MacroExpansionOptions())
    expanded_forms: list[Form] = []
    for form in forms:
        try:
            expanded_forms.append(
                cast(
                    Form,
                    await _macroexpand_form(
                        form,
                        context,
                        depth=0,
                    ),
                )
            )
        except EvaluationError as e:
            context.diagnostics.append(
                Diagnostic(
                    e.message,
                    line=e.line,
                    column=e.column,
                )
            )
    return MacroExpansion(expanded_forms, tuple(context.diagnostics), tuple(context.traces))


def macroexpand_source(
    source: str,
    env: Environment | None = None,
    *,
    source_name: str | None = None,
    options: MacroExpansionOptions | None = None,
) -> MacroExpansion:
    return cast(
        MacroExpansion,
        run_async(macroexpand_source_async(source, env, source_name=source_name, options=options)),
    )


async def macroexpand_source_async(
    source: str,
    env: Environment | None = None,
    *,
    source_name: str | None = None,
    options: MacroExpansionOptions | None = None,
) -> MacroExpansion:
    try:
        forms = read(source, source_name=source_name)
    except ReaderSyntaxError as e:
        return MacroExpansion(
            [],
            (Diagnostic(str(e), "error", line=e.line, column=e.column),),
        )
    return await macroexpand_async(forms, env, options=options)


@dataclass(slots=True)
class MacroExpansionContext:
    env: Environment
    options: MacroExpansionOptions
    scope: MacroScope
    macro_namespace: dict[Symbol, MacroDefinition]
    module_macro_namespace: dict[str, dict[Symbol, MacroDefinition]]
    diagnostics: list[Diagnostic] = field(default_factory=list)
    traces: list[MacroExpansionTrace] = field(default_factory=list)
    generated_symbols: list[Symbol] = field(default_factory=list)
    active_expansions: list[Symbol] = field(default_factory=list)
    gensym_counter: int = 0
    hygiene_counter: int = 0

    @classmethod
    def create(
        cls,
        env: Environment,
        options: MacroExpansionOptions,
    ) -> MacroExpansionContext:
        macro_namespace = _macro_namespace(env)
        module_macro_namespace = _module_macro_namespace(env)
        scope = MacroScope(publish_definitions=True, bindings=dict(macro_namespace))
        return cls(env, options, scope, macro_namespace, module_macro_namespace)

    def child_scope(self) -> MacroExpansionContext:
        return MacroExpansionContext(
            self.env,
            self.options,
            self.scope.child(),
            self.macro_namespace,
            self.module_macro_namespace,
            self.diagnostics,
            self.traces,
            self.generated_symbols,
            self.active_expansions,
            self.gensym_counter,
            self.hygiene_counter,
        )

    def child_scope_with_env(self, env: Environment) -> MacroExpansionContext:
        return MacroExpansionContext(
            env,
            self.options,
            self.scope.child(),
            self.macro_namespace,
            self.module_macro_namespace,
            self.diagnostics,
            self.traces,
            self.generated_symbols,
            self.active_expansions,
            self.gensym_counter,
            self.hygiene_counter,
        )

    def sync_from(self, child: MacroExpansionContext) -> None:
        self.gensym_counter = child.gensym_counter
        self.hygiene_counter = child.hygiene_counter

    def define_macro(self, name: Symbol, value: MacroDefinition) -> None:
        self.scope.define(name, value)
        if self.scope.publish_definitions:
            self.macro_namespace[name] = value

    def resolve_macro(self, name: Symbol) -> MacroDefinition | None:
        return self.scope.lookup(name)

    def define_module_macros(
        self,
        module_name: Symbol,
        macros: dict[Symbol, MacroDefinition],
    ) -> None:
        self.module_macro_namespace[module_name.name] = dict(macros)

    def services(self) -> MacroExpansionServices:
        return MacroExpansionServices(self.gensym, self.capture)

    def gensym(self, prefix: object | None = None) -> Symbol:
        self.gensym_counter += 1
        base = _gensym_prefix(prefix)
        symbol = Symbol(f"__qy_gensym_{base}_{self.gensym_counter}")
        self.generated_symbols.append(symbol)
        return symbol

    def capture(self, value: object) -> CapturedForm:
        return CapturedForm(value)

    def fresh_hygienic_symbol(self, prefix: object | None, *, category: str) -> Symbol:
        self.hygiene_counter += 1
        base = _gensym_prefix(prefix)
        return Symbol(f"__qy_hygiene_{category}_{base}_{self.hygiene_counter}")

    def expansion_chain(self) -> tuple[str, ...]:
        return tuple(symbol.name for symbol in self.active_expansions)


async def _macroexpand_form(
    form: object,
    context: MacroExpansionContext,
    *,
    depth: int,
) -> object:
    if depth > context.options.max_depth:
        raise QyArityError(
            f"macro expansion exceeded {context.options.max_depth} nested expansions",
            span=get_span(form),
        )
    if not isinstance(form, tuple) or isinstance(form, DottedTuple) or not form:
        return form

    operator = form[0]
    args = tuple(form[1:])
    if operator == Symbol("quote"):
        return form
    if operator == Symbol("quasiquote"):
        if len(args) != 1:
            return form
        return await _macroexpand_form(
            _expand_quasiquote(args[0], depth=0),
            context,
            depth=depth,
        )
    if operator == Symbol("macro"):
        _define_macro(form, context)
        return form
    if operator == Symbol("from"):
        _import_macros_from_form(form, context)
        return form
    if operator == Symbol("let"):
        return await _macroexpand_body_form(form, context, depth=depth, body_start=2)
    if operator == Symbol("module"):
        return await _macroexpand_module_form(form, context, depth=depth)
    if operator == Symbol("imports"):
        return _macroexpand_imports_form(form, context)
    if operator == Symbol("lambda"):
        return await _macroexpand_body_form(form, context, depth=depth, body_start=2)
    if operator == Symbol("defun"):
        return await _macroexpand_body_form(form, context, depth=depth, body_start=3)
    if operator == Symbol("define"):
        return await _macroexpand_body_form(form, context, depth=depth, body_start=2)

    if isinstance(operator, Symbol):
        if (value := context.resolve_macro(operator)) is not None:
            context.active_expansions.append(operator)
            try:
                before_symbols = len(context.generated_symbols)
                expanded, renames = await _expand_macro(value, args, context, form)
                generated = tuple(context.generated_symbols[before_symbols:])
                context.traces.append(
                    MacroExpansionTrace(
                        operator,
                        get_span(form),
                        get_span(expanded),
                        depth + 1,
                        form,
                        expanded,
                        generated,
                        renames,
                    )
                )
                return await _macroexpand_form(
                    expanded,
                    context,
                    depth=depth + 1,
                )
            finally:
                context.active_expansions.pop()

    return _tuple_like(
        form,
        [await _macroexpand_form(item, context, depth=depth) for item in form],
    )


async def _macroexpand_body_form(
    form: tuple[object, ...],
    context: MacroExpansionContext,
    *,
    depth: int,
    body_start: int,
) -> tuple[object, ...]:
    if len(form) <= body_start:
        return _tuple_like(
            form,
            [await _macroexpand_form(item, context, depth=depth) for item in form],
        )
    prefix = [await _macroexpand_form(item, context, depth=depth) for item in form[:body_start]]
    body_context = context.child_scope()
    body = []
    for item in form[body_start:]:
        body.append(await _macroexpand_form(item, body_context, depth=depth))
    context.sync_from(body_context)
    return _tuple_like(form, [*prefix, *body])


async def _macroexpand_module_form(
    form: tuple[object, ...],
    context: MacroExpansionContext,
    *,
    depth: int,
) -> tuple[object, ...]:
    if len(form) <= 2:
        return _tuple_like(
            form,
            [await _macroexpand_form(item, context, depth=depth) for item in form],
        )

    prefix = [await _macroexpand_form(item, context, depth=depth) for item in form[:2]]

    # Build a module-local env pre-populated with compile-time placeholder bindings for
    # defun/defeffect forms in the module body.  This lets macros defined later
    # in the same module body capture those symbols in their definition-site closure.
    module_env = context.env.child()
    _prepopulate_module_locals(form[2:], module_env)
    body_context = context.child_scope_with_env(module_env)

    body: list[object] = []
    for item in form[2:]:
        if _is_special_form(item, "imports"):
            body.append(_macroexpand_imports_form(cast(tuple[object, ...], item), body_context))
            continue
        body.append(await _macroexpand_form(item, body_context, depth=depth))

    context.sync_from(body_context)
    module_name = prefix[1]
    if isinstance(module_name, Symbol):
        exported_macros = _exported_module_macros(form[2:], body_context)
        context.define_module_macros(module_name, exported_macros)
    return _tuple_like(form, [*prefix, *body])


def _prepopulate_module_locals(body: tuple[object, ...], env: Environment) -> None:
    from qy.runtime_values import EffectDefinition
    from qy.runtime_values import UserFunction

    for item in body:
        if not isinstance(item, tuple) or not item:
            continue
        operator = item[0]
        if operator == Symbol("defun") and len(item) >= 3 and isinstance(item[1], Symbol):
            name = item[1]
            params_form = item[2] if len(item) > 2 else ()
            params = tuple(
                p
                for p in (params_form if isinstance(params_form, tuple) else ())
                if isinstance(p, Symbol)
            )
            body_forms = tuple(item[3:])
            env.define(name, UserFunction(name, params, body_forms, env))
        elif operator == Symbol("defeffect") and len(item) >= 2 and isinstance(item[1], Symbol):
            env.define(item[1], EffectDefinition(item[1], resumable=True))


def _macroexpand_imports_form(
    form: tuple[object, ...],
    context: MacroExpansionContext,
) -> tuple[object, ...]:
    for item in form[1:]:
        if isinstance(item, tuple):
            _import_macros_from_form(item, context)
    return form


def _expand_quasiquote(form: object, *, depth: int = 0) -> object:
    if isinstance(form, tuple) and not isinstance(form, DottedTuple) and form:
        op = form[0]
        if op == Symbol("unquote"):
            if depth == 0:
                return form[1] if len(form) == 2 else form
            return (Symbol("list"), Symbol("unquote"), _expand_quasiquote(form[1], depth=depth - 1))
        if op == Symbol("quasiquote"):
            inner = _expand_quasiquote(form[1] if len(form) == 2 else form, depth=depth + 1)
            return (Symbol("list"), Symbol("quasiquote"), inner)
        return _expand_quasiquote_tuple(form, depth=depth)
    if isinstance(form, DottedTuple):
        return (Symbol("quote"), form)
    return (Symbol("quote"), form)


def _expand_quasiquote_tuple(form: tuple[object, ...], *, depth: int) -> object:
    if not form:
        return (Symbol("quote"), ())
    head_form = form[0]
    tail = form[1:]
    if (
        isinstance(head_form, tuple)
        and not isinstance(head_form, DottedTuple)
        and head_form
        and head_form[0] == Symbol("unquote-splicing")
        and depth == 0
    ):
        spliced = head_form[1] if len(head_form) == 2 else head_form
        rest = _expand_quasiquote_tuple(tail, depth=depth)
        return (Symbol("qy-append"), spliced, rest)
    head = _expand_quasiquote(head_form, depth=depth)
    rest = _expand_quasiquote_tuple(tail, depth=depth)
    return (Symbol("cons"), head, rest)


async def _expand_macro(
    macro: MacroDefinition,
    args: tuple[object, ...],
    context: MacroExpansionContext,
    form: object,
) -> tuple[object, tuple[MacroRename, ...]]:
    chain = _format_expansion_chain(context)
    try:
        expanded = await macro.expand(args, context.services())
    except QyEffectSignal as e:
        if context.options.effect_policy == "allow":
            raise
        raise QyRuntimeError(
            f"macro {macro.name.name!r} attempted compile-time effect {e.effect!r}{chain}",
            span=get_span(form),
            cause=e,
            metadata={"macro": macro.name.name, "effect": e.effect},
        ) from e
    except EvaluationError as e:
        raise QyRuntimeError(
            f"macro {macro.name.name!r} failed during compile-time evaluation: {e.message}{chain}",
            span=get_span(form),
            cause=e,
            metadata={
                "macro": macro.name.name,
                "available_compile_time_bindings": compile_time_binding_names(macro.closure),
            },
        ) from e
    return apply_hygiene(_normalize_macro_result(expanded), macro, args, context)


def _define_macro(form: tuple[object, ...], context: MacroExpansionContext) -> None:
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
    context.define_macro(
        name,
        MacroDefinition(
            name,
            tuple(param_symbols),
            tuple(body),
            compile_time_environment(context.env),
        ),
    )


def _gensym_prefix(prefix: object | None) -> str:
    if prefix is None:
        return "sym"
    if isinstance(prefix, Symbol):
        prefix = prefix.name
    return "".join(char if char.isalnum() or char == "_" else "_" for char in str(prefix)) or "sym"


def _normalize_macro_result(value: object) -> object:
    if isinstance(value, CapturedForm):
        return CapturedForm(_normalize_macro_result(value.value))
    if isinstance(value, QyCons):
        return tuple(_normalize_macro_result(item) for item in qy_cons_to_tuple(value))
    if isinstance(value, tuple):
        return _tuple_like(value, [_normalize_macro_result(item) for item in value])
    return value


def _macro_namespace(env: Environment) -> dict[Symbol, MacroDefinition]:
    try:
        value = env.cache_lookup(_MACRO_NAMESPACE_CACHE_KEY)
    except KeyError:
        value = env.cache_define(_MACRO_NAMESPACE_CACHE_KEY, {})
    return cast(dict[Symbol, MacroDefinition], value)


def _module_macro_namespace(env: Environment) -> dict[str, dict[Symbol, MacroDefinition]]:
    try:
        value = env.cache_lookup(_MODULE_MACRO_NAMESPACE_CACHE_KEY)
    except KeyError:
        value = env.cache_define(_MODULE_MACRO_NAMESPACE_CACHE_KEY, {})
    return cast(dict[str, dict[Symbol, MacroDefinition]], value)


def _import_macros_from_form(form: tuple[object, ...], context: MacroExpansionContext) -> None:
    try:
        module_name, specs = parse_from_import(form)
    except ValueError as e:
        context.diagnostics.append(Diagnostic(str(e), line=_line_of(form), column=_column_of(form)))
        return

    try:
        macros = _resolve_module_macros(module_name, context)
    except KeyError as e:
        context.diagnostics.append(
            Diagnostic(str(e), line=_line_of(module_name), column=_column_of(module_name))
        )
        return

    for spec in specs:
        macro = macros.get(spec.name)
        if macro is not None:
            context.scope.define(spec.alias, macro)


def _resolve_module_macros(
    module_name: Symbol,
    context: MacroExpansionContext,
) -> dict[Symbol, MacroDefinition]:
    if module_name.name in context.module_macro_namespace:
        return context.module_macro_namespace[module_name.name]
    module = load_module(module_name.name)
    return {
        symbol: value
        for symbol, value in module.macro_exports.items()
        if isinstance(value, MacroDefinition)
    }


def _exported_module_macros(
    body: tuple[object, ...],
    context: MacroExpansionContext,
) -> dict[Symbol, MacroDefinition]:
    local_bindings = context.scope.bindings or {}
    export_names = _parse_export_names(body)
    if export_names:
        return {
            name: local_bindings[name]
            for name in export_names
            if isinstance(local_bindings.get(name), MacroDefinition)
        }
    return {
        name: value for name, value in local_bindings.items() if isinstance(value, MacroDefinition)
    }


def _parse_export_names(forms: tuple[object, ...]) -> tuple[Symbol, ...]:
    names: list[Symbol] = []
    for form in forms:
        if _is_special_form(form, "exports"):
            assert isinstance(form, tuple)
            names.extend(_parse_export_items(tuple(form[1:])))
    return tuple(names)


def _parse_export_items(items: tuple[object, ...]) -> list[Symbol]:
    names: list[Symbol] = []
    for item in items:
        if isinstance(item, tuple):
            names.extend(_parse_export_items(item))
        elif isinstance(item, Symbol):
            names.append(item)
    return names


def _is_special_form(form: object, name: str) -> bool:
    return isinstance(form, tuple) and len(form) > 0 and form[0] == Symbol(name)


def _line_of(form: object) -> int | None:
    span = get_span(form)
    return None if span is None else span.line


def _column_of(form: object) -> int | None:
    span = get_span(form)
    return None if span is None else span.column


def _format_expansion_chain(context: MacroExpansionContext) -> str:
    chain = context.expansion_chain()
    if len(chain) <= 1:
        return ""
    return f"; expansion chain: {' -> '.join(chain)}"
