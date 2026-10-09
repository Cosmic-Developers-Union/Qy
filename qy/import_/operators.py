# coding: utf-8

from __future__ import annotations

from qy.core.operators import ScopeOperator
from qy.core.symbol_utils import ensure_symbol
from qy.core.syntax import Symbol
from qy.core.syntax import car
from qy.core.syntax import cdr
from qy.core.syntax import chain_to_list
from qy.core.syntax import is_chain
from qy.core.syntax import is_nil
from qy.core.syntax import list_to_chain
from qy.errors import EvaluationError
from qy.errors import QyArityError
from qy.import_.module import StandardModule
from qy.import_.parse import parse_from_import
from qy.import_.registry import load_module_async
from qy.import_.registry import register_module
from qy.session.runtime_space import RuntimeSpace as Environment
from qy.vm.instance.machine import evaluate_form_async as evaluate_async


def _is_special_form(form: object, name: str) -> bool:
    """``form`` 是否为 head 是 ``Symbol(name)`` 的 chain。.

    raw AST 只有 symbol / chain / nil；这里不接受宿主 tuple。
    """
    if not is_chain(form):
        return False
    return car(form) == Symbol(name)


def _parse_export_names(items: object) -> list[Symbol]:
    """把 ``exports`` 的尾部 chain 展平为一组符号名。."""
    if is_nil(items):
        return []
    if not is_chain(items):
        raise TypeError(f"exports expects a chain, got {type(items).__name__}")
    names: list[Symbol] = []
    for item in chain_to_list(items):
        if is_chain(item):
            names.extend(_parse_export_names(item))
            continue
        names.append(ensure_symbol(item, "module export"))
    return names


async def _module(args: tuple[object, ...], env: Environment) -> object:
    if not args:
        raise QyArityError("module expects a name and body")

    from qy.import_.loader import cache_source_module
    from qy.import_.loader import lookup_source_module
    from qy.macro import MacroDefinition
    from qy.project.module import build_provisional_module

    name, *body = args
    name = ensure_symbol(name, "module name")
    module_env = env.child()
    export_names: list[Symbol] = []

    for form in body:
        if _is_special_form(form, "exports"):
            export_names.extend(_parse_export_names(cdr(form)))
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
        provisional = build_provisional_module(list_to_chain([Symbol("module"), name, *body]), env)
    if provisional is not None:
        macro_exports = {**dict(provisional.macro_exports), **macro_exports}

    module = StandardModule(name.name, exports, macro_exports)

    register_module(module)
    cache_source_module(module, env)
    return env.define_once(name, module)


async def _from_import(args: tuple[object, ...], env: Environment) -> object:
    from qy.import_.from_fold import fold_import

    try:
        module_name, specs = parse_from_import(list_to_chain([Symbol("from"), *args]))
        source_module = await load_module_async(module_name.name)
        fold_import(env, module_name.name, specs, source_module)
    except (KeyError, ValueError) as e:
        raise EvaluationError(str(e)) from e

    return None


def operators() -> dict[Symbol, object]:
    return {
        Symbol("from"): ScopeOperator("from", _from_import, "从模块导入算子到当前作用域。"),
        Symbol("module"): ScopeOperator("module", _module, "定义并注册模块。"),
    }
