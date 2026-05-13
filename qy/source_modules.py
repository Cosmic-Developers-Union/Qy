# coding: utf-8

from __future__ import annotations

from typing import cast

from qy.compile_time import compile_time_environment
from qy.evaluator import ComponentDefinition
from qy.evaluator import EffectDefinition
from qy.evaluator import Environment
from qy.evaluator import UserFunction
from qy.macro import MacroDefinition
from qy.reader import Symbol
from qy.stdlib import load_module
from qy.stdlib.imports import parse_from_import
from qy.stdlib.module import StandardModule

__all__ = [
    "build_provisional_module",
    "cache_source_module",
    "lookup_source_module",
    "remember_source_module",
    "resolve_known_module",
]


def cache_source_module(module: StandardModule, env: Environment) -> StandardModule:
    _source_module_cache(env)[module.name] = module
    return module


def lookup_source_module(name: str, env: Environment) -> StandardModule | None:
    return _source_module_cache(env).get(name)


_SOURCE_MODULE_CACHE_KEY = ("qy", "source_modules")


def remember_source_module(form: object, env: Environment) -> StandardModule | None:
    module = build_provisional_module(form, env)
    if module is None:
        return None
    return cache_source_module(module, env)


def resolve_known_module(name: str, env: Environment) -> StandardModule:
    modules = _source_module_cache(env)
    if name in modules:
        return modules[name]
    return load_module(name)


def build_provisional_module(form: object, env: Environment) -> StandardModule | None:
    if not _is_special_form(form, "module"):
        return None
    assert isinstance(form, tuple)
    if len(form) < 2 or not isinstance(form[1], Symbol):
        return None

    name = form[1]
    body = tuple(form[2:])
    locals_map: dict[Symbol, object] = {}
    export_names: list[Symbol] = []

    for item in body:
        if _is_special_form(item, "exports"):
            assert isinstance(item, tuple)
            export_names.extend(_parse_export_items(tuple(item[1:])))
            continue
        if _is_special_form(item, "imports"):
            assert isinstance(item, tuple)
            _populate_imported_bindings(tuple(item[1:]), env, locals_map)
            continue
        if not isinstance(item, tuple) or not item:
            continue
        operator = item[0]
        if operator == Symbol("defun") and len(item) >= 3 and isinstance(item[1], Symbol):
            locals_map[item[1]] = UserFunction(item[1], _parameter_symbols(item[2]), (None,), env)
            continue
        if operator == Symbol("component") and len(item) >= 3 and isinstance(item[1], Symbol):
            locals_map[item[1]] = ComponentDefinition(
                item[1],
                _parameter_symbols(item[2]),
                (None,),
                env,
            )
            continue
        if operator == Symbol("macro") and len(item) >= 4 and isinstance(item[1], Symbol):
            locals_map[item[1]] = MacroDefinition(
                item[1],
                _parameter_symbols(item[2]),
                tuple(item[3:]),
                compile_time_environment(env),
            )
            continue
        if operator == Symbol("defeffect") and len(item) >= 2 and isinstance(item[1], Symbol):
            locals_map[item[1]] = EffectDefinition(item[1], resumable=_effect_resumable(item[2:]))
            continue
        if operator == Symbol("module") and len(item) >= 2 and isinstance(item[1], Symbol):
            nested = build_provisional_module(item, env)
            if nested is not None:
                locals_map[item[1]] = nested

    selected = (
        {
            export_name: locals_map[export_name]
            for export_name in export_names
            if export_name in locals_map
        }
        if export_names
        else dict(locals_map)
    )
    runtime_exports = {
        symbol: value
        for symbol, value in selected.items()
        if not isinstance(value, MacroDefinition)
    }
    macro_exports = {
        symbol: value for symbol, value in selected.items() if isinstance(value, MacroDefinition)
    }
    return StandardModule(name.name, runtime_exports, macro_exports)


def _source_module_cache(env: Environment) -> dict[str, StandardModule]:
    try:
        value = env.cache_lookup(_SOURCE_MODULE_CACHE_KEY)
    except KeyError:
        value = env.cache_define(_SOURCE_MODULE_CACHE_KEY, {})
    return cast(dict[str, StandardModule], value)


def _populate_imported_bindings(
    import_forms: tuple[object, ...],
    env: Environment,
    locals_map: dict[Symbol, object],
) -> None:
    for import_form in import_forms:
        if not isinstance(import_form, tuple):
            continue
        try:
            module_name, specs = parse_from_import(import_form)
            source_module = resolve_known_module(module_name.name, env)
        except (KeyError, ValueError):
            continue
        for spec in specs:
            if spec.name in source_module.exports:
                locals_map[spec.alias] = source_module.resolve(spec.name)
            elif spec.name in source_module.macro_exports:
                locals_map[spec.alias] = source_module.resolve_macro(spec.name)


def _parameter_symbols(params: object) -> tuple[Symbol, ...]:
    if not isinstance(params, tuple):
        return ()
    return tuple(param for param in params if isinstance(param, Symbol))


def _parse_export_items(items: tuple[object, ...]) -> list[Symbol]:
    names: list[Symbol] = []
    for item in items:
        if isinstance(item, tuple):
            names.extend(_parse_export_items(item))
        elif isinstance(item, Symbol):
            names.append(item)
    return names


def _effect_resumable(options: tuple[object, ...]) -> bool:
    if len(options) == 2 and options[0] == Symbol(":resumable") and options[1] == Symbol("false"):
        return False
    return True


def _is_special_form(form: object, name: str) -> bool:
    return isinstance(form, tuple) and len(form) > 0 and form[0] == Symbol(name)
