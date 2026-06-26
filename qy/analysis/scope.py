# coding: utf-8
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from typing import cast

if TYPE_CHECKING:
    from collections.abc import Iterable

from qy.analysis.refs import operator_kind_for_value
from qy.analysis.refs import value_signature
from qy.analysis.refs import value_type
from qy.analysis.refs import value_uses_eager_arguments
from qy.core import OperatorKind
from qy.core import TypeName
from qy.core.operator_signature import OperatorSignature
from qy.core.syntax import chain_to_list
from qy.core.syntax import is_chain
from qy.core.syntax import is_nil
from qy.diag import Diagnostic
from qy.frontend.reader import Symbol
from qy.import_.loader import resolve_known_module
from qy.import_.parse import parse_from_import
from qy.project.module import remember_source_module
from qy.session.runtime_space import RuntimeSpace as Environment


@dataclass(frozen=True, slots=True)
class Binding:
    type_name: TypeName
    operator_kind: OperatorKind | None = None
    eager_arguments: bool = True
    signature: OperatorSignature | None = None


@dataclass(frozen=True, slots=True)
class Scope:
    bindings: dict[Symbol, Binding] | None = None

    def has_local(self, symbol: Symbol) -> bool:
        return self.bindings is not None and symbol in self.bindings

    def define(
        self,
        symbol: Symbol,
        type_name: TypeName = "any",
        *,
        operator_kind: OperatorKind | None = None,
        eager_arguments: bool = True,
        signature: OperatorSignature | None = None,
    ) -> Scope:
        bindings = dict(self.bindings or {})
        bindings[symbol] = Binding(type_name, operator_kind, eager_arguments, signature)
        return Scope(bindings)

    def lookup(self, symbol: Symbol) -> Binding | None:
        if self.bindings is None:
            return None
        return self.bindings.get(symbol)


def scope_from_environment(env: Environment) -> Scope:
    scope = Scope()
    for frame in env.pre_symbol_space_chain():
        for symbol, value in frame.bindings.items():
            scope = scope.define(
                symbol,
                value_type(value),
                operator_kind=operator_kind_for_value(value),
                eager_arguments=value_uses_eager_arguments(value),
                signature=value_signature(value),
            )
    return scope


def scope_after_form(form: object, env: Environment, scope: Scope) -> Scope:
    if not is_chain(form):
        return scope

    try:
        form_list = list(cast("Iterable[object]", form))
        if not form_list:
            return scope
    except ValueError:
        return scope

    if len(form_list) >= 2 and form_list[0] == Symbol("defun") and isinstance(form_list[1], Symbol):
        if scope.has_local(form_list[1]):
            return scope
        return scope.define(form_list[1], "function")
    if (
        len(form_list) >= 2
        and form_list[0] == Symbol("define")
        and isinstance(form_list[1], Symbol)
    ):
        if scope.has_local(form_list[1]):
            return scope
        # 检查是否是 (define name (component ...))
        if len(form_list) >= 3 and is_chain(form_list[2]):
            try:
                value_list = list(cast("Iterable[object]", form_list[2]))
                if value_list and value_list[0] == Symbol("component"):
                    # component 生成宏，所以类型是 operator
                    return scope.define(
                        form_list[1], "operator", operator_kind="meta", eager_arguments=False
                    )
            except (ValueError, TypeError):
                pass
        return scope.define(form_list[1], "any")
    if (
        len(form_list) >= 2
        and form_list[0] == Symbol("defeffect")
        and isinstance(form_list[1], Symbol)
    ):
        if scope.has_local(form_list[1]):
            return scope
        return scope.define(form_list[1], "effect")
    if len(form_list) >= 2 and form_list[0] == Symbol("macro") and isinstance(form_list[1], Symbol):
        if scope.has_local(form_list[1]):
            return scope
        return scope.define(form_list[1], "operator", operator_kind="meta", eager_arguments=False)
    if (
        len(form_list) >= 2
        and form_list[0] == Symbol("module")
        and isinstance(form_list[1], Symbol)
    ):
        remember_source_module(form, env)
        if scope.has_local(form_list[1]):
            return scope
        return scope.define(form_list[1])
    if form_list[0] != Symbol("from"):
        return scope

    try:
        module_name, specs = parse_from_import(form)
        source_module = resolve_known_module(module_name.name, env)
    except (KeyError, ValueError):
        return scope

    next_scope = scope
    for spec in specs:
        if spec.name in source_module.exports:
            value = source_module.resolve(spec.name)
        elif spec.name in source_module.macro_exports:
            value = source_module.resolve_macro(spec.name)
        else:
            continue
        next_scope = next_scope.define(
            spec.alias,
            value_type(value),
            operator_kind=operator_kind_for_value(value),
            eager_arguments=value_uses_eager_arguments(value),
            signature=value_signature(value),
        )
    return next_scope


def predeclare_callable_definitions(body: tuple[object, ...], scope: Scope) -> Scope:
    next_scope = scope
    for expression in body:
        if not isinstance(expression, tuple) or len(expression) < 2:
            continue
        if expression[0] != Symbol("defun"):
            continue
        name = expression[1]
        if isinstance(name, Symbol) and not next_scope.has_local(name):
            next_scope = next_scope.define(name, "function")
    return next_scope


def scope_with_parameters(
    params: object,
    scope: Scope,
    diagnostics: list[Diagnostic],
    context: str,
) -> Scope:
    if not (is_chain(params) or isinstance(params, tuple) or is_nil(params)):
        diagnostics.append(Diagnostic(f"{context} parameters must be a list, got {params!r}"))
        return scope

    params_list = (
        chain_to_list(params)
        if is_chain(params)
        else (list(params) if isinstance(params, tuple) else [])
    )
    next_scope = scope
    for param in params_list:
        if isinstance(param, Symbol):
            next_scope = next_scope.define(param)
        else:
            diagnostics.append(Diagnostic(f"{context} parameter must be a symbol, got {param!r}"))
    return next_scope
