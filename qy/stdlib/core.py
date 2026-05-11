# coding: utf-8

from __future__ import annotations

import asyncio
import inspect
import operator

from qy.evaluator import ComponentDefinition
from qy.evaluator import ControlOperator
from qy.evaluator import EffectOperator
from qy.evaluator import Environment
from qy.evaluator import EvaluationError
from qy.evaluator import MetaOperator
from qy.evaluator import PureOperator
from qy.evaluator import ScopeOperator
from qy.evaluator import UserFunction
from qy.evaluator import ensure_symbol
from qy.evaluator import evaluate_async
from qy.evaluator import evaluate_body_async
from qy.reader import Symbol
from qy.stdlib.imports import parse_from_import
from qy.stdlib.module import StandardModule


def module() -> StandardModule:
    return StandardModule(
        "qy.core",
        {
            Symbol("+"): PureOperator("+", _add, "Add numbers."),
            Symbol("-"): PureOperator("-", _sub, "Subtract numbers, or negate one number."),
            Symbol("*"): PureOperator("*", _mul, "Multiply numbers."),
            Symbol("/"): PureOperator("/", _div, "Divide numbers, or invert one number."),
            Symbol("await"): EffectOperator("await", _await, "Await spawned async work."),
            Symbol("atom"): PureOperator(
                "atom", _atom, "Return true if the value is not a non-empty list."
            ),
            Symbol("cache"): EffectOperator("cache", _cache, "Cache one evaluated expression."),
            Symbol("car"): PureOperator("car", _car, "Return the first item of a non-empty list."),
            Symbol("cdr"): PureOperator(
                "cdr", _cdr, "Return all but the first item of a non-empty list."
            ),
            Symbol("cond"): ControlOperator(
                "cond", _cond, "Evaluate the first truthy condition branch."
            ),
            Symbol("cons"): PureOperator("cons", _cons, "Prepend an item to a list."),
            Symbol("component"): ScopeOperator(
                "component", _component, "Define a reusable component in the current scope."
            ),
            Symbol("defun"): ScopeOperator(
                "defun", _defun, "Define a function in the current environment."
            ),
            Symbol("eq"): PureOperator("eq", _eq, "Compare atoms and empty lists."),
            Symbol("from"): ScopeOperator(
                "from", _from_import, "Import standard module operators into the current scope."
            ),
            Symbol("lambda"): ScopeOperator("lambda", _lambda, "Create an anonymous function."),
            Symbol("let"): ScopeOperator("let", _let, "Evaluate a body in a local lexical scope."),
            Symbol("module"): ScopeOperator("module", _module, "Define and register a module."),
            Symbol("parallel"): EffectOperator(
                "parallel", _parallel, "Evaluate expressions concurrently with asyncio tasks."
            ),
            Symbol("quote"): MetaOperator(
                "quote", _quote, "Return one expression without evaluating it."
            ),
            Symbol("spawn"): EffectOperator("spawn", _spawn, "Create an asyncio task."),
        },
    )


def _ensure_number(value: object) -> int | float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise EvaluationError(f"expected number, got {value!r}")
    return value


def _ensure_tuple(value: object) -> tuple[object, ...]:
    if not isinstance(value, tuple):
        raise EvaluationError(f"expected tuple, got {value!r}")
    return value


def _truthy(value: object) -> bool:
    return value not in (False, None, ())


def _add(*args: object) -> int | float:
    return sum(_ensure_number(arg) for arg in args)


def _sub(first: object, *rest: object) -> int | float:
    first_number = _ensure_number(first)
    if not rest:
        return -first_number
    return first_number - sum(_ensure_number(arg) for arg in rest)


def _mul(*args: object) -> int | float:
    result: int | float = 1
    for arg in args:
        result = operator.mul(result, _ensure_number(arg))
    return result


def _div(first: object, *rest: object) -> int | float:
    result = _ensure_number(first)
    if not rest:
        return 1 / result
    for arg in rest:
        result = operator.truediv(result, _ensure_number(arg))
    return result


def _quote(expression: tuple[object, ...], env: Environment) -> object:
    del env
    args = expression[1:]
    if len(args) != 1:
        raise EvaluationError("quote expects exactly one argument")
    return args[0]


def _atom(value: object) -> bool:
    return not isinstance(value, tuple) or len(value) == 0


def _eq(left: object, right: object) -> bool:
    if isinstance(left, tuple) and isinstance(right, tuple):
        return len(left) == 0 and len(right) == 0
    return left == right


def _car(value: object) -> object:
    items = _ensure_tuple(value)
    if not items:
        raise EvaluationError("car expects a non-empty tuple")
    return items[0]


def _cdr(value: object) -> tuple[object, ...]:
    items = _ensure_tuple(value)
    if not items:
        raise EvaluationError("cdr expects a non-empty tuple")
    return items[1:]


def _cons(head: object, tail: object) -> tuple[object, ...]:
    return (head, *_ensure_tuple(tail))


async def _cond(args: tuple[object, ...], env: Environment) -> object:
    for clause in args:
        if not isinstance(clause, tuple) or len(clause) != 2:
            raise EvaluationError(f"cond clause must be a pair, got {clause!r}")
        condition, result = clause
        if _truthy(await evaluate_async(condition, env)):
            return await evaluate_async(result, env)
    return None


async def _let(args: tuple[object, ...], env: Environment) -> object:
    if len(args) < 2:
        raise EvaluationError("let expects bindings and at least one body expression")

    bindings, *body = args
    if not isinstance(bindings, tuple):
        raise EvaluationError(f"let bindings must be a list, got {bindings!r}")

    local_env = env.child()
    for binding in bindings:
        if not isinstance(binding, tuple) or len(binding) != 2:
            raise EvaluationError(f"let binding must be a pair, got {binding!r}")
        name, expression = binding
        local_env.define(
            ensure_symbol(name, "let binding name"),
            await evaluate_async(expression, local_env),
        )

    return await evaluate_body_async(tuple(body), local_env)


def _lambda(args: tuple[object, ...], env: Environment) -> object:
    if len(args) < 2:
        raise EvaluationError("lambda expects a parameter list and body")

    params, *body = args
    param_symbols = _ensure_parameter_list(params, "lambda")
    return UserFunction(Symbol("<lambda>"), param_symbols, tuple(body), env)


def _defun(args: tuple[object, ...], env: Environment) -> object:
    if len(args) < 3:
        raise EvaluationError("defun expects a name, parameter list, and body")

    name, params, *body = args
    name = ensure_symbol(name, "defun name")
    param_symbols = _ensure_parameter_list(params, "defun")
    function = UserFunction(name, param_symbols, tuple(body), env)
    return env.define(name, function)


def _component(args: tuple[object, ...], env: Environment) -> object:
    if len(args) < 3:
        raise EvaluationError("component expects a name, parameter list, and body")

    name, params, *body = args
    name = ensure_symbol(name, "component name")
    param_symbols = _ensure_parameter_list(params, "component")
    component = ComponentDefinition(name, param_symbols, tuple(body), env)
    return env.define(name, component)


async def _module(args: tuple[object, ...], env: Environment) -> object:
    if not args:
        raise EvaluationError("module expects a name and body")

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

    if export_names:
        exports = {export_name: module_env.resolve(export_name) for export_name in export_names}
    else:
        exports = module_env.local_bindings()

    module = StandardModule(name.name, exports)

    from qy.stdlib import register_module

    register_module(module)
    return env.define(name, module)


async def _from_import(args: tuple[object, ...], env: Environment) -> object:
    try:
        module_name, specs = parse_from_import((Symbol("from"), *args))
        from qy.stdlib import load_module_async

        source_module = await load_module_async(module_name.name)
        for spec in specs:
            env.define(spec.alias, source_module.resolve(spec.name))
    except (KeyError, ValueError) as e:
        raise EvaluationError(str(e)) from e

    return None


async def _parallel(args: tuple[object, ...], env: Environment) -> tuple[object, ...]:
    tasks = [asyncio.create_task(evaluate_async(arg, env)) for arg in args]
    return tuple(await asyncio.gather(*tasks))


async def _cache(args: tuple[object, ...], env: Environment) -> object:
    if len(args) != 1:
        raise EvaluationError(f"cache expects exactly one argument, got {len(args)}")

    key = _cache_key(args[0])
    try:
        return await _await_cached_value(env.cache_lookup(key))
    except KeyError:
        pass

    task = asyncio.create_task(evaluate_async(args[0], env))
    env.cache_define(key, task)
    try:
        result = await task
    except Exception:
        env.cache_discard(key)
        raise
    env.cache_define(key, result)
    return result


def _spawn(args: tuple[object, ...], env: Environment) -> asyncio.Task[object]:
    if len(args) != 1:
        raise EvaluationError(f"spawn expects exactly one argument, got {len(args)}")
    return asyncio.create_task(evaluate_async(args[0], env))


async def _await(args: tuple[object, ...], env: Environment) -> object:
    if not args:
        raise EvaluationError("await expects at least one argument")

    values: list[object] = []
    for arg in args:
        value = await evaluate_async(arg, env)
        values.append(await _await_cached_value(value))

    if len(values) == 1:
        return values[0]
    return tuple(values)


def _ensure_parameter_list(value: object, context: str) -> tuple[Symbol, ...]:
    if not isinstance(value, tuple):
        raise EvaluationError(f"{context} parameters must be a tuple of symbols, got {value!r}")
    return tuple(_ensure_symbol_parameter(param, context) for param in value)


def _ensure_symbol_parameter(value: object, context: str) -> Symbol:
    if not isinstance(value, Symbol):
        raise EvaluationError(f"{context} parameters must be symbols, got {value!r}")
    return value


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
        raise EvaluationError(f"module import must be a from form, got {form!r}")
    if form[0] != Symbol("from"):
        raise EvaluationError(f"module import must start with from, got {form!r}")
    await evaluate_async(form, env)


def _cache_key(expression: object) -> object:
    try:
        hash(expression)
    except TypeError:
        return repr(expression)
    return expression


async def _await_cached_value(value: object) -> object:
    if inspect.isawaitable(value):
        return await value
    return value
