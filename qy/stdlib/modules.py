# coding: utf-8

from __future__ import annotations

from qy.errors import QyArityError
from qy.errors import QyTypeError
from qy.evaluator import Environment
from qy.evaluator import EvaluationError
from qy.evaluator import ScopeOperator
from qy.evaluator import ensure_symbol
from qy.evaluator import evaluate_async
from qy.reader import Symbol
from qy.reader import get_span
from qy.stdlib.imports import parse_from_import
from qy.stdlib.module import StandardModule


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


async def _evaluate_module_import(form: object, env: Environment) -> None:
    if not isinstance(form, tuple) or not form:
        raise QyTypeError(f"module import must be a from form, got {form!r}", span=get_span(form))
    if form[0] != Symbol("from"):
        raise QyTypeError(f"module import must start with from, got {form!r}", span=get_span(form))
    await evaluate_async(form, env)


async def _module(args: tuple[object, ...], env: Environment) -> object:
    if not args:
        raise QyArityError("module expects a name and body")

    from qy.macro import MacroDefinition
    from qy.source_modules import build_provisional_module
    from qy.source_modules import cache_source_module

    name, *body = args
    name = ensure_symbol(name, "module name")
    module_env = env.child()
    export_names: list[Symbol] = []

    for form in body:
        if _is_special_form(form, "exports"):
            assert isinstance(form, tuple)
            export_names.extend(_parse_export_names(form[1:]))
            continue
        if _is_special_form(form, "imports"):
            assert isinstance(form, tuple)
            for import_form in form[1:]:
                await _evaluate_module_import(import_form, module_env)
            continue
        await evaluate_async(form, module_env)

    selected = (
        {export_name: module_env.resolve(export_name) for export_name in export_names}
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
    provisional = build_provisional_module((Symbol("module"), name, *body), env)
    if provisional is not None:
        macro_exports = {**dict(provisional.macro_exports), **macro_exports}

    module = StandardModule(name.name, exports, macro_exports)

    from qy.stdlib import register_module

    register_module(module)
    cache_source_module(module, env)
    return env.define_once(name, module)


async def _from_import(args: tuple[object, ...], env: Environment) -> object:
    try:
        module_name, specs = parse_from_import((Symbol("from"), *args))
        from qy.stdlib import load_module_async

        source_module = await load_module_async(module_name.name)
        for spec in specs:
            if spec.name in source_module.exports:
                env.define_once(spec.alias, source_module.resolve(spec.name))
            elif spec.name in source_module.macro_exports:
                continue
            else:
                raise KeyError(f"module {module_name.name!r} has no export {spec.name.name!r}")
    except (KeyError, ValueError) as e:
        raise EvaluationError(str(e)) from e

    return None


def operators() -> dict[Symbol, object]:
    return {
        Symbol("from"): ScopeOperator("from", _from_import, "从模块导入算子到当前作用域。"),
        Symbol("module"): ScopeOperator("module", _module, "定义并注册模块。"),
    }
