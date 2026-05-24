# coding: utf-8
# QY_DELETE_AFTER_SEMANTIC_REPLACEMENT: target=qy/std/*

from __future__ import annotations

from typing import TYPE_CHECKING
from typing import cast

if TYPE_CHECKING:
    from collections.abc import Sized

from qy.core.operators import ControlOperator
from qy.core.operators import MetaOperator
from qy.core.operators import PureOperator
from qy.core.operators import ScopeOperator
from qy.core.syntax import car
from qy.core.syntax import cdr
from qy.core.syntax import chain_to_list
from qy.core.syntax import is_chain
from qy.core.syntax import is_nil
from qy.core.syntax import list_to_chain
from qy.environment import Environment
from qy.errors import QyArityError
from qy.errors import QyTypeError
from qy.frontend.reader import Symbol
from qy.frontend.reader import get_span
from qy.sem.runtime import UserFunction
from qy.symbol_utils import ensure_symbol
from qy.values import QY_NIL
from qy.values import QY_T
from qy.vm.instance.machine import evaluate_form_async as evaluate_async
from qy.vm.instance.machine import evaluate_form_body_async as evaluate_body_async


def _to_list(form: object) -> list[object]:
    """将 Chain 或 tuple 转换为 Python list。."""
    if is_chain(form):
        return chain_to_list(form)
    if isinstance(form, tuple):
        return list(form)
    return []


def _get_args(form: object) -> list[object]:
    """获取 form 的参数（除第一个元素外的所有元素）。."""
    if is_chain(form):
        if is_nil(form):
            return []
        rest = cdr(form)
        if is_nil(rest):
            return []
        if is_chain(rest):
            return chain_to_list(rest)
        # improper list
        return [rest]
    if isinstance(form, tuple):
        return list(form[1:])
    return []


def _form_length(form: object) -> int:
    """获取 form 的长度。."""
    if is_chain(form):
        if is_nil(form):
            return 0
        try:
            return len(cast("Sized", form))
        except ValueError:
            # improper list
            count = 0
            current = form
            while is_chain(current):
                count += 1
                current = cdr(current)
            return count + 1
    if isinstance(form, tuple):
        return len(form)
    return 0


def _truthy(value: object) -> bool:
    """nil-only truthiness: only QY_NIL is false.

    This is the language-core truth model used by cond.
    The standard-profile ``truthy`` operator provides complex truthiness.
    """
    return value is not QY_NIL


def _complex_truthy(value: object) -> object:
    """Standard-profile complex truthiness operator.

    Returns QY_T for broadly-truthy values, QY_NIL for broadly-falsy values.
    Handles Python host values (False, None, 0, "", empty containers)
    alongside Qy values (QY_NIL, empty chain).
    """
    if value is QY_NIL:
        return QY_NIL
    if value is None:
        return QY_NIL
    if value is False:
        return QY_NIL
    if value == ():
        return QY_NIL
    if isinstance(value, int | float) and not isinstance(value, bool) and value == 0:
        return QY_NIL
    if isinstance(value, str) and value == "":
        return QY_NIL
    if isinstance(value, list | dict | set) and len(value) == 0:
        return QY_NIL
    return QY_T


def _ensure_parameter_list(value: object, context: str) -> tuple[Symbol, ...]:
    if is_chain(value):
        params = chain_to_list(value)
        return tuple(_ensure_symbol_parameter(param, context) for param in params)
    if not isinstance(value, tuple):
        raise QyTypeError(
            f"{context} parameters must be a list of symbols, got {value!r}",
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


def _quote(expression: object, env: Environment) -> object:
    del env
    args = _get_args(expression)
    if len(args) != 1:
        raise QyArityError("quote expects exactly one argument", span=get_span(expression))
    return _quote_data(args[0])


def _quote_data(value: object) -> object:
    if is_chain(value):
        result_items = []
        current = value
        while is_chain(current):
            result_items.append(_quote_data(car(current)))
            current = cdr(current)

        if not is_nil(current):
            # Improper list
            return list_to_chain(result_items, tail=_quote_data(current))
        return list_to_chain(result_items)
    if isinstance(value, tuple):
        return list_to_chain(_quote_data(item) for item in value)
    return value


async def _eval(expression: object, env: Environment) -> object:
    args = _get_args(expression)
    if len(args) != 1:
        raise QyArityError(
            f"eval expects exactly one argument, got {len(args)}",
            span=get_span(expression),
            metadata={"expected": 1, "actual": len(args)},
        )
    form = await evaluate_async(args[0], env)
    return await evaluate_async(form, env)


def _macro(expression: object, env: Environment) -> object:
    length = _form_length(expression)
    if length < 4:
        raise QyArityError(
            "macro expects a name, parameter list, and body", span=get_span(expression)
        )

    args = _get_args(expression)
    name = args[0]
    params = args[1]
    # body = args[2:]  # not used
    ensure_symbol(name, "macro name")
    _ensure_parameter_list(params, "macro")
    del env
    return None


async def _cond(args: object, env: Environment) -> object:
    clauses = _to_list(args)
    for clause in clauses:
        clause_list = None
        if is_chain(clause):
            try:
                clause_list = chain_to_list(clause)
            except ValueError:
                pass
        elif isinstance(clause, tuple):
            clause_list = list(clause)

        if clause_list is None or len(clause_list) != 2:
            raise QyTypeError(
                f"cond clause must be a pair, got {clause!r}",
                span=get_span(clause),
                metadata={"clause": clause},
            )
        condition, result = clause_list
        if _truthy(await evaluate_async(condition, env)):
            return await evaluate_async(result, env)
    return QY_NIL


async def _let(args: object, env: Environment) -> object:
    args_list = _to_list(args)
    if len(args_list) < 2:
        raise QyArityError("let expects bindings and at least one body expression")

    bindings = args_list[0]
    body = args_list[1:]

    if not (is_chain(bindings) or isinstance(bindings, tuple)):
        raise QyTypeError(
            f"let bindings must be a list, got {bindings!r}",
            span=get_span(bindings),
        )

    bindings_list = _to_list(bindings)
    local_env = env.child()
    for binding in bindings_list:
        binding_list = None
        if is_chain(binding):
            try:
                binding_list = chain_to_list(binding)
            except ValueError:
                pass
        elif isinstance(binding, tuple):
            binding_list = list(binding)

        if binding_list is None or len(binding_list) != 2:
            raise QyTypeError(
                f"let binding must be a pair, got {binding!r}",
                span=get_span(binding),
            )
        name, expression = binding_list
        local_env.define(
            ensure_symbol(name, "let binding name"),
            await evaluate_async(expression, local_env),
        )

    return await evaluate_body_async(tuple(body), local_env)


def _lambda(args: object, env: Environment) -> object:
    args_list = _to_list(args)
    if len(args_list) < 2:
        raise QyArityError("lambda expects a parameter list and body")

    params = args_list[0]
    body = args_list[1:]
    param_symbols = _ensure_parameter_list(params, "lambda")
    return UserFunction(Symbol("<lambda>"), param_symbols, tuple(body), env)


async def _define(args: object, env: Environment) -> object:
    args_list = _to_list(args)
    if len(args_list) != 2:
        raise QyArityError("define expects a name and a value")
    name_form, value_form = args_list
    name = ensure_symbol(name_form, "define name")
    if name.name.startswith("'") and len(name.name) > 1:
        name = Symbol(name.name[1:])
    value = await evaluate_async(value_form, env)
    return env.define(name, value)


def _defun(args: object, env: Environment) -> object:
    args_list = _to_list(args)
    if len(args_list) < 3:
        raise QyArityError("defun expects a name, parameter list, and body")

    name = args_list[0]
    params = args_list[1]
    body = args_list[2:]
    name = ensure_symbol(name, "defun name")
    param_symbols = _ensure_parameter_list(params, "defun")
    function = UserFunction(name, param_symbols, tuple(body), env)
    return env.define(name, function)


def _component(args: object, env: Environment) -> object:
    """组合多个算子成为一个新算子。.

    (component op1 op2 ... opn) 创建一个新算子，当调用时：
    - 第一个参数传给 op1
    - 剩余参数传给 opn，得到结果 rn
    - 然后将结果向前传递：op(n-1) 接收 r(n-1) 和 rn 的结果
    - 最终 op1 接收第一个参数和 op2 的结果

    例如：(component define lambda) 创建的算子，
    调用 (new-op name params body) 时等价于 (define name (lambda params body))。

    component 返回一个宏，这样它可以在宏展开阶段工作。
    """
    from qy.core.syntax import list_to_chain
    from qy.macro import MacroDefinition

    args_list = _to_list(args)
    if len(args_list) < 2:
        raise QyArityError(
            "component expects at least 2 operators",
            span=get_span(args),
        )

    # 获取算子的符号名称
    # 参数可能是符号（未求值）或算子对象（已求值）
    operator_symbols = []
    for op_form in args_list:
        if isinstance(op_form, Symbol):
            operator_symbols.append(op_form)
        elif hasattr(op_form, "name") and isinstance(op_form.name, str):
            # 算子对象，提取其名称
            operator_symbols.append(Symbol(op_form.name))
        else:
            raise QyTypeError(
                f"component expects operators or operator symbols, got {op_form!r}",
                span=get_span(op_form),
            )

    # 创建宏的 body
    # 宏接收参数 &body args，然后生成组合的调用
    # 例如：(component define lambda) 生成的宏，
    # 当调用 (macro-name a b c) 时，应该展开为 (define a (lambda b c))

    if len(operator_symbols) == 2:
        op1, op2 = operator_symbols
        # 生成：(cons 'op1 (cons (car args) (cons (cons 'op2 (cdr args)) nil)))
        # 这会构造 (op1 first-arg (op2 rest-args...))
        macro_body = (
            list_to_chain(
                [
                    Symbol("cons"),
                    list_to_chain([Symbol("quote"), op1]),
                    list_to_chain(
                        [
                            Symbol("cons"),
                            list_to_chain([Symbol("car"), Symbol("args")]),
                            list_to_chain(
                                [
                                    Symbol("cons"),
                                    list_to_chain(
                                        [
                                            Symbol("cons"),
                                            list_to_chain([Symbol("quote"), op2]),
                                            list_to_chain([Symbol("cdr"), Symbol("args")]),
                                        ]
                                    ),
                                    Symbol("nil"),
                                ]
                            ),
                        ]
                    ),
                ]
            ),
        )
    else:
        # 多个算子的情况更复杂，暂时不支持
        raise QyArityError(
            "component currently only supports 2 operators",
            span=get_span(args),
        )

    # 返回一个宏定义
    return MacroDefinition(
        Symbol("<component-macro>"),
        (),  # 固定参数
        macro_body,
        env,
        rest_param=Symbol("args"),  # 可变参数
    )


def _this(args: object, env: Environment) -> object:
    del args
    return env


def _slot(args: object, env: Environment) -> object:
    del args, env
    from qy.core.symbol_space import BindingSlot

    return BindingSlot(Symbol("<slot>"))


async def _bind(args: object, env: Environment) -> object:
    args_list = _to_list(args)
    if len(args_list) != 3:
        raise QyArityError("bind expects a symbol, value, and slot")
    name_datum, value, _slot_value = args_list
    name = ensure_symbol(name_datum, "bind name")
    if name.name.startswith("'") and len(name.name) > 1:
        name = Symbol(name.name[1:])
    env.define(name, value)
    return value


def operators() -> dict[Symbol, object]:
    return {
        Symbol("cond"): ControlOperator("cond", _cond, "求值第一个 truthy 条件分支。"),
        Symbol("component"): MetaOperator("component", _component, "组合多个算子成为一个新算子。"),
        Symbol("define"): ScopeOperator(
            "define", _define, "在当前 symbol-space 一次性绑定 symbol。"
        ),
        Symbol("defun"): ScopeOperator("defun", _defun, "在当前环境定义函数。"),
        Symbol("eval"): MetaOperator("eval", _eval, "求值一个符号 form。"),
        Symbol("lambda"): ScopeOperator("lambda", _lambda, "创建匿名函数。"),
        Symbol("let"): ScopeOperator("let", _let, "在词法局部作用域中求值 body。"),
        Symbol("macro"): MetaOperator("macro", _macro, "定义接收未求值 form 并展开的宏。"),
        Symbol("quote"): MetaOperator("quote", _quote, "返回一个表达式，不求值。"),
        Symbol("truthy"): PureOperator(
            "truthy", _complex_truthy, "标准 profile 复杂真值判断；返回 T 或 nil。"
        ),
        Symbol("this"): ScopeOperator("this", _this, "返回当前 symbol-space。"),
        Symbol("slot"): ScopeOperator("slot", _slot, "创建绑定槽位。"),
        Symbol("bind"): ScopeOperator("bind", _bind, "将 symbol 与 value 绑定到指定 slot。"),
    }


def legacy_operators() -> dict[Symbol, object]:
    return {}
