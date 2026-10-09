# coding: utf-8
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from qy.core.syntax import Symbol
from qy.core.syntax import chain_to_list
from qy.core.syntax import is_chain
from qy.import_.from_fold import iter_selected_exports
from qy.import_.loader import cache_source_module
from qy.import_.loader import resolve_known_module
from qy.import_.module import StandardModule
from qy.import_.parse import parse_from_import
from qy.macro import MacroDefinition
from qy.sem.runtime import EffectDefinition

if TYPE_CHECKING:
    from qy.session.runtime_space import RuntimeSpace as Environment

__all__ = [
    "ProvisionalBinding",
    "ProvisionalFunction",
    "build_provisional_module",
    "remember_source_module",
]


@dataclass(frozen=True, slots=True)
class ProvisionalFunction:
    """编译期命名空间标记：模块里有一个 defun 成员。.

    它**不承载运行期值**——模块的运行期函数由 `module` 算子执行模块体后得到
    （`qy/vm/instance/machine.py::_run_module`），provisional 记录只用于提供
    `macro_exports` 与名字集合。
    """

    name: Symbol
    params: tuple[Symbol, ...]


@dataclass(frozen=True, slots=True)
class ProvisionalBinding:
    """编译期命名空间标记：模块里有一个非函数 ``define`` 成员。.

    它**不承载运行期值**——运行期值由执行模块体后得到；标记只用于让同源单元的
    ``(from ...)`` 在 HIR lowering 解析到该导出名。
    """

    name: Symbol


def remember_source_module(form: object, env: Environment) -> StandardModule | None:
    module = build_provisional_module(form, env)
    if module is None:
        return None
    from qy.import_.loader import _source_module_cache

    modules = _source_module_cache(env)
    if module.name in modules:
        return modules[module.name]
    return cache_source_module(module, env)


def build_provisional_module(form: object, env: Environment) -> StandardModule | None:
    if not _is_special_form(form, "module"):
        return None

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
            if isinstance(item, tuple):
                export_items = tuple(item[1:])
            elif is_chain(item):
                export_items = tuple(chain_to_list(item)[1:])
            else:
                continue
            export_names.extend(_parse_export_items(export_items))
            continue

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
            locals_map[item_list[1]] = ProvisionalFunction(
                item_list[1], _parameter_symbols(item_list[2])
            )
            continue
        if (
            operator == Symbol("define")
            and len(item_list) >= 3
            and isinstance(item_list[1], Symbol)
        ):
            define_name = item_list[1]
            if define_name.name.startswith("'") and len(define_name.name) > 1:
                define_name = Symbol(define_name.name[1:])
            value_form = item_list[2]
            value_items = chain_to_list(value_form) if is_chain(value_form) else []
            if value_items and value_items[0] == Symbol("lambda") and len(value_items) >= 2:
                locals_map[define_name] = ProvisionalFunction(
                    define_name, _parameter_symbols(value_items[1])
                )
            else:
                locals_map[define_name] = ProvisionalBinding(define_name)
            continue
        if operator == Symbol("macro") and len(item_list) >= 4 and isinstance(item_list[1], Symbol):
            locals_map[item_list[1]] = MacroDefinition(
                item_list[1],
                _parameter_symbols(item_list[2]),
                tuple(item_list[3:]),
                env,
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


def _populate_imported_bindings(
    import_forms: tuple[object, ...],
    env: Environment,
    locals_map: dict[Symbol, object],
) -> None:
    for import_form in import_forms:
        # raw AST 只有 chain；parse_from_import 也只接受 chain。
        try:
            module_name, specs = parse_from_import(import_form)
            source_module = resolve_known_module(module_name.name, env)
        except (KeyError, ValueError):
            continue
        # 与运行时 fold / register VM 共用同一 fold primitive（选择逻辑单源）。
        for alias, binding, _is_macro in iter_selected_exports(
            module_name.name, specs, source_module, require=False
        ):
            locals_map[alias] = binding


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
    if isinstance(form, tuple):
        return len(form) > 0 and form[0] == Symbol(name)
    if is_chain(form):
        items = chain_to_list(form)
        return len(items) > 0 and items[0] == Symbol(name)
    return False
