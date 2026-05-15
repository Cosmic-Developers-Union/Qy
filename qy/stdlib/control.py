# coding: utf-8

from __future__ import annotations

from qy.environment import Environment
from qy.errors import QyArityError
from qy.errors import QyTypeError
from qy.eval_runtime import evaluate_async
from qy.eval_runtime import evaluate_body_async
from qy.operators import ControlOperator
from qy.operators import MetaOperator
from qy.operators import ScopeOperator
from qy.reader import DottedTuple
from qy.reader import Symbol
from qy.reader import get_span
from qy.runtime_values import UserFunction
from qy.symbol_utils import ensure_symbol
from qy.values import QY_NIL
from qy.values import list_to_qy_cons


def _truthy(value: object) -> bool:
    return value is not False and value is not None and value is not QY_NIL and value != ()


def _ensure_parameter_list(value: object, context: str) -> tuple[Symbol, ...]:
    if not isinstance(value, tuple):
        raise QyTypeError(
            f"{context} parameters must be a tuple of symbols, got {value!r}",
            span=get_span(value),
        )
    return tuple(_ensure_symbol_parameter(param, context) for param in value)


def _ensure_symbol_parameter(value: object, context: str) -> Symbol:
    if not isinstance(value, Symbol):
        raise QyTypeError(
            f"{context} parameters must be symbols, got {value!r}",
            span=get_span(value),
        )
    return value


def _quote(expression: tuple[object, ...], env: Environment) -> object:
    del env
    args = expression[1:]
    if len(args) != 1:
        raise QyArityError("quote expects exactly one argument", span=get_span(expression))
    return _quote_data(args[0])


def _quote_data(value: object) -> object:
    if isinstance(value, DottedTuple):
        return list_to_qy_cons((_quote_data(item) for item in value), _quote_data(value.tail))
    if isinstance(value, tuple):
        return list_to_qy_cons(_quote_data(item) for item in value)
    return value


async def _eval(expression: tuple[object, ...], env: Environment) -> object:
    args = expression[1:]
    if len(args) != 1:
        raise QyArityError(
            f"eval expects exactly one argument, got {len(args)}",
            span=get_span(expression),
            metadata={"expected": 1, "actual": len(args)},
        )
    form = await evaluate_async(args[0], env)
    return await evaluate_async(form, env)


def _macro(expression: tuple[object, ...], env: Environment) -> object:
    if len(expression) < 4:
        raise QyArityError(
            "macro expects a name, parameter list, and body", span=get_span(expression)
        )

    _, name, params, *body = expression
    ensure_symbol(name, "macro name")
    _ensure_parameter_list(params, "macro")
    del body, env
    return None


async def _cond(args: tuple[object, ...], env: Environment) -> object:
    for clause in args:
        if not isinstance(clause, tuple) or len(clause) != 2:
            raise QyTypeError(
                f"cond clause must be a pair, got {clause!r}",
                span=get_span(clause),
                metadata={"clause": clause},
            )
        condition, result = clause
        if _truthy(await evaluate_async(condition, env)):
            return await evaluate_async(result, env)
    return None


async def _let(args: tuple[object, ...], env: Environment) -> object:
    if len(args) < 2:
        raise QyArityError("let expects bindings and at least one body expression")

    bindings, *body = args
    if not isinstance(bindings, tuple):
        raise QyTypeError(
            f"let bindings must be a list, got {bindings!r}",
            span=get_span(bindings),
        )

    local_env = env.child()
    for binding in bindings:
        if not isinstance(binding, tuple) or len(binding) != 2:
            raise QyTypeError(
                f"let binding must be a pair, got {binding!r}",
                span=get_span(binding),
            )
        name, expression = binding
        local_env.define(
            ensure_symbol(name, "let binding name"),
            await evaluate_async(expression, local_env),
        )

    return await evaluate_body_async(tuple(body), local_env)


def _lambda(args: tuple[object, ...], env: Environment) -> object:
    if len(args) < 2:
        raise QyArityError("lambda expects a parameter list and body")

    params, *body = args
    param_symbols = _ensure_parameter_list(params, "lambda")
    return UserFunction(Symbol("<lambda>"), param_symbols, tuple(body), env)


async def _define(args: tuple[object, ...], env: Environment) -> object:
    if len(args) != 2:
        raise QyArityError("define expects a name and a value")
    name_form, value_form = args
    name = ensure_symbol(name_form, "define name")
    value = await evaluate_async(value_form, env)
    return env.define_once(name, value)


def _defun(args: tuple[object, ...], env: Environment) -> object:
    if len(args) < 3:
        raise QyArityError("defun expects a name, parameter list, and body")

    name, params, *body = args
    name = ensure_symbol(name, "defun name")
    param_symbols = _ensure_parameter_list(params, "defun")
    function = UserFunction(name, param_symbols, tuple(body), env)
    return env.define(name, function)


def _component(args: tuple[object, ...], env: Environment) -> object:
    if len(args) < 3:
        raise QyArityError("component expects a name, parameter list, and body")

    name, params, *body = args
    name = ensure_symbol(name, "component name")
    param_symbols = _ensure_parameter_list(params, "component")
    component = UserFunction(name, param_symbols, tuple(body), env)
    return env.define(name, component)


def operators() -> dict[Symbol, object]:
    return {
        Symbol("cond"): ControlOperator("cond", _cond, "求值第一个 truthy 条件分支。"),
        Symbol("define"): ScopeOperator(
            "define", _define, "在当前 symbol-space 一次性绑定 symbol。"
        ),
        Symbol("defun"): ScopeOperator("defun", _defun, "在当前环境定义函数。"),
        Symbol("eval"): MetaOperator("eval", _eval, "求值一个符号 form。"),
        Symbol("lambda"): ScopeOperator("lambda", _lambda, "创建匿名函数。"),
        Symbol("let"): ScopeOperator("let", _let, "在词法局部作用域中求值 body。"),
        Symbol("macro"): MetaOperator("macro", _macro, "定义接收未求值 form 并展开的宏。"),
        Symbol("quote"): MetaOperator("quote", _quote, "返回一个表达式，不求值。"),
    }


def legacy_operators() -> dict[Symbol, object]:
    return {
        Symbol("component"): ScopeOperator("component", _component, "在当前作用域定义可复用组件。"),
    }
