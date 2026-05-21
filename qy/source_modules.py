# coding: utf-8
# QY_DELETE_AFTER_MIGRATION: target=qy/import_/loader.py + qy/project/module.py

from __future__ import annotations

from typing import cast

from qy.compile_time import compile_time_environment
from qy.core.syntax import chain_to_list
from qy.core.syntax import is_chain
from qy.environment import Environment
from qy.macro import MacroDefinition
from qy.reader import Symbol
from qy.sem.runtime import EffectDefinition
from qy.sem.runtime import UserFunction
from qy.std import load_module
from qy.std.imports import parse_from_import
from qy.std.module import StandardModule

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
    # Don't overwrite existing cache (宏展开阶段已缓存原始 AST)
    modules = _source_module_cache(env)
    if module.name in modules:
        return modules[module.name]
    return cache_source_module(module, env)


def resolve_known_module(name: str, env: Environment) -> StandardModule:
    modules = _source_module_cache(env)
    if name in modules:
        return modules[name]
    return load_module(name)


def build_provisional_module(form: object, env: Environment) -> StandardModule | None:
    if not _is_special_form(form, "module"):
        return None

    # 统一转换为 list 处理
    if isinstance(form, tuple):
        items = list(form)
    elif is_chain(form):
        items = chain_to_list(form)
    else:
        return None

    if len(items) < 2 or not isinstance(items[1], Symbol):
        return None

    name = items[1]
    body = items[2:]
    locals_map: dict[Symbol, object] = {}
    export_names: list[Symbol] = []

    for item in body:
        if _is_special_form(item, "exports"):
            # 转换为 list
            if isinstance(item, tuple):
                export_items = tuple(item[1:])
            elif is_chain(item):
                export_items = tuple(chain_to_list(item)[1:])
            else:
                continue
            export_names.extend(_parse_export_items(export_items))
            continue

        # 转换为 list 以统一处理
        if isinstance(item, tuple):
            item_list = list(item)
        elif is_chain(item):
            item_list = chain_to_list(item)
        else:
            continue

        if not item_list:
            continue

        operator = item_list[0]
        if operator == Symbol("from"):
            _populate_imported_bindings((item,), env, locals_map)
            continue
        if operator == Symbol("defun") and len(item_list) >= 3 and isinstance(item_list[1], Symbol):
            locals_map[item_list[1]] = UserFunction(
                item_list[1], _parameter_symbols(item_list[2]), (None,), env
            )
            continue
        if operator == Symbol("macro") and len(item_list) >= 4 and isinstance(item_list[1], Symbol):
            locals_map[item_list[1]] = MacroDefinition(
                item_list[1],
                _parameter_symbols(item_list[2]),
                tuple(item_list[3:]),
                compile_time_environment(env),
            )
            continue
        if (
            operator == Symbol("defeffect")
            and len(item_list) >= 2
            and isinstance(item_list[1], Symbol)
        ):
            locals_map[item_list[1]] = EffectDefinition(
                item_list[1], resumable=_effect_resumable(tuple(item_list[2:]))
            )
            continue
        if (
            operator == Symbol("module")
            and len(item_list) >= 2
            and isinstance(item_list[1], Symbol)
        ):
            nested = build_provisional_module(item, env)
            if nested is not None:
                locals_map[item_list[1]] = nested

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
        # 转换为 tuple 以供 parse_from_import 使用
        if is_chain(import_form):
            import_form = tuple(chain_to_list(import_form))
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
    if isinstance(params, tuple):
        return tuple(param for param in params if isinstance(param, Symbol))
    if is_chain(params):
        items = chain_to_list(params)
        return tuple(param for param in items if isinstance(param, Symbol))
    return ()


def _parse_export_items(items: tuple[object, ...]) -> list[Symbol]:
    names: list[Symbol] = []
    for item in items:
        if isinstance(item, tuple):
            names.extend(_parse_export_items(item))
        elif is_chain(item):
            names.extend(_parse_export_items(tuple(chain_to_list(item))))
        elif isinstance(item, Symbol):
            names.append(item)
    return names


def _effect_resumable(options: tuple[object, ...]) -> bool:
    if len(options) == 2 and options[0] == Symbol(":resumable") and options[1] == Symbol("false"):
        return False
    return True


def _is_special_form(form: object, name: str) -> bool:
    """检查 form 是否为特定的 special form.

    支持 tuple 和 Chain 两种形式。
    """
    if isinstance(form, tuple):
        return len(form) > 0 and form[0] == Symbol(name)
    if is_chain(form):
        items = chain_to_list(form)
        return len(items) > 0 and items[0] == Symbol(name)
    return False
