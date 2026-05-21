# coding: utf-8

from __future__ import annotations

from qy.environment import Environment
from qy.errors import EvaluationError
from qy.errors import QyArityError
from qy.eval_runtime import evaluate_async
from qy.operators import ScopeOperator
from qy.reader import Symbol
from qy.std.imports import parse_from_import
from qy.std.module import StandardModule
from qy.symbol_utils import ensure_symbol


def _is_special_form(form: object, name: str) -> bool:
    return isinstance(form, tuple) and len(form) > 0 and form[0] == Symbol(name)


def _parse_export_names(items: tuple[object, ...]) -> list[Symbol]:
    names: list[Symbol] = []
    for item in items:
        if isinstance(item, tuple):
            names.extend(_parse_export_names(item))
            continue
        names.append(ensure_symbol(item, "module export"))
    return names


async def _module(args: tuple[object, ...], env: Environment) -> object:
    if not args:
        raise QyArityError("module expects a name and body")

    from qy.macro import MacroDefinition
    from qy.source_modules import build_provisional_module
    from qy.source_modules import cache_source_module
    from qy.source_modules import lookup_source_module

    name, *body = args
    name = ensure_symbol(name, "module name")
    module_env = env.child()
    export_names: list[Symbol] = []

    for form in body:
        if _is_special_form(form, "exports"):
            assert isinstance(form, tuple)
            export_names.extend(_parse_export_names(form[1:]))
            continue
        await evaluate_async(form, module_env)

    selected = (
        {
            export_name: module_env.resolve(export_name)
            for export_name in export_names
            if export_name in module_env.local_bindings()
        }
        if export_names
        else module_env.local_bindings()
    )
    exports = {
        symbol: value
        for symbol, value in selected.items()
        if not isinstance(value, MacroDefinition)
    }
    macro_exports = {
        symbol: value for symbol, value in selected.items() if isinstance(value, MacroDefinition)
    }
    # 优先使用缓存的 provisional 模块（在宏展开阶段缓存）
    provisional = lookup_source_module(name.name, env)
    if provisional is None:
        # 如果没有缓存，尝试从当前 body 构建（可能已经展开，宏定义被移除）
        provisional = build_provisional_module((Symbol("module"), name, *body), env)
    if provisional is not None:
        macro_exports = {**dict(provisional.macro_exports), **macro_exports}

    module = StandardModule(name.name, exports, macro_exports)

    from qy.std import register_module

    register_module(module)
    cache_source_module(module, env)
    return env.define_once(name, module)


async def _from_import(args: tuple[object, ...], env: Environment) -> object:
    try:
        module_name, specs = parse_from_import((Symbol("from"), *args))
        from qy.std import load_module_async

        source_module = await load_module_async(module_name.name)
        runtime_specs = [spec for spec in specs if spec.name in source_module.exports]
        macro_only = all(spec.name in source_module.macro_exports for spec in specs)
        if not runtime_specs and not macro_only:
            missing = [spec.name.name for spec in specs]
            raise KeyError(f"module {module_name.name!r} has no export {missing[0]!r}")
        if runtime_specs:
            alias_bindings: dict[Symbol, object] = {}
            for spec in runtime_specs:
                alias_bindings[spec.alias] = source_module.exports[spec.name]
            env.fold_from(
                alias_bindings,
                [spec.alias for spec in runtime_specs],
            )
    except (KeyError, ValueError) as e:
        raise EvaluationError(str(e)) from e

    return None


def operators() -> dict[Symbol, object]:
    return {
        Symbol("from"): ScopeOperator("from", _from_import, "从模块导入算子到当前作用域。"),
        Symbol("module"): ScopeOperator("module", _module, "定义并注册模块。"),
    }
