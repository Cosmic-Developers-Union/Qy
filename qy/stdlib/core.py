# coding: utf-8

from __future__ import annotations

import asyncio
import builtins
import hashlib
import inspect
import keyword
import linecache
import operator
import textwrap
from collections.abc import Awaitable
from collections.abc import Callable
from typing import cast

from qy.errors import QyAggregateError
from qy.errors import QyArityError
from qy.errors import QyCancelledError
from qy.errors import QyEffectSignal
from qy.errors import QyError
from qy.errors import QyPythonError
from qy.errors import QyRuntimeError
from qy.errors import QyTypeError
from qy.evaluator import ComponentDefinition
from qy.evaluator import ControlOperator
from qy.evaluator import EffectDefinition
from qy.evaluator import EffectOperator
from qy.evaluator import Environment
from qy.evaluator import EvaluationError
from qy.evaluator import HostObjectRef
from qy.evaluator import MacroDefinition
from qy.evaluator import MetaOperator
from qy.evaluator import PureOperator
from qy.evaluator import QyContinuation
from qy.evaluator import ScopeOperator
from qy.evaluator import UserFunction
from qy.evaluator import ensure_symbol
from qy.evaluator import evaluate_async
from qy.evaluator import evaluate_body_async
from qy.reader import DottedTuple
from qy.reader import Symbol
from qy.reader import get_span
from qy.stdlib.imports import parse_from_import
from qy.stdlib.module import StandardModule
from qy.values import QY_EMPTY_LIST
from qy.values import QyCons
from qy.values import list_to_qy_cons
from qy.values import map_qy_cons
from qy.values import qy_cons_to_tuple

_PY_FUNCTION_NAME = "__qy_py__"
_PY_FUNCTION_CACHE: dict[tuple[str, tuple[str, ...]], Callable[..., Awaitable[object]]] = {}


def module() -> StandardModule:
    return StandardModule(
        "qy.core",
        {
            Symbol("+"): PureOperator("+", _add, "数字求和。"),
            Symbol("-"): PureOperator("-", _sub, "数字相减；单参数时取负。"),
            Symbol("*"): PureOperator("*", _mul, "数字相乘。"),
            Symbol("/"): PureOperator("/", _div, "数字相除；单参数时取倒数。"),
            Symbol("assert"): EffectOperator(
                "assert", _special_effect_form, "断言 debug 条件；失败时执行 assert-failed。"
            ),
            Symbol("await"): EffectOperator("await", _await, "等待一个或多个异步值。"),
            Symbol("atom"): PureOperator(
                "atom", _atom, "如果值不是非空 cons 或 tuple，则返回 true。"
            ),
            Symbol("cache"): EffectOperator("cache", _cache, "缓存一个表达式的求值结果。"),
            Symbol("car"): PureOperator("car", _car, "返回 cons/tuple/list 的第一个元素。"),
            Symbol("cdr"): PureOperator(
                "cdr", _cdr, "返回 cons/tuple/list 除第一个元素外的剩余部分。"
            ),
            Symbol("cond"): ControlOperator("cond", _cond, "求值第一个 truthy 条件分支。"),
            Symbol("cons"): PureOperator(
                "cons", _cons, "构造 cons；对 Python tuple/list 保持同类拼接。"
            ),
            Symbol("dict"): PureOperator(
                "dict", _dict, "用 key/value 参数构造 dict。", _evaluate_data_args
            ),
            Symbol("dict?"): PureOperator("dict?", _dict_predicate, "判断值是否为 dict。"),
            Symbol("component"): ScopeOperator(
                "component", _component, "在当前作用域定义可复用组件。"
            ),
            Symbol("defeffect"): ScopeOperator(
                "defeffect", _defeffect, "声明 effect，供 perform/handle 和分析器使用。"
            ),
            Symbol("defun"): ScopeOperator("defun", _defun, "在当前环境定义函数。"),
            Symbol("eq"): PureOperator("eq", _eq, "比较原子；非空 cons 按 identity 比较。"),
            Symbol("eval"): MetaOperator("eval", _eval, "求值一个符号 form。"),
            Symbol("from"): ScopeOperator("from", _from_import, "从模块导入算子到当前作用域。"),
            Symbol("get"): PureOperator(
                "get", _get, "从 tuple/list/dict 获取项。", _evaluate_lookup_args
            ),
            Symbol("has?"): PureOperator(
                "has?",
                _has,
                "判断 collection 是否包含 key、index 或成员。",
                _evaluate_lookup_args,
            ),
            Symbol("lambda"): ScopeOperator("lambda", _lambda, "创建匿名函数。"),
            Symbol("len"): PureOperator("len", _len, "返回 collection 长度。"),
            Symbol("let"): ScopeOperator("let", _let, "在词法局部作用域中求值 body。"),
            Symbol("list"): PureOperator("list", _list, "构造 list。", _evaluate_data_args),
            Symbol("list?"): PureOperator("list?", _list_predicate, "判断值是否为 list。"),
            Symbol("macro"): MetaOperator("macro", _macro, "定义接收未求值 form 并展开的宏。"),
            Symbol("module"): ScopeOperator("module", _module, "定义并注册模块。"),
            Symbol("parallel"): EffectOperator(
                "parallel", _parallel, "用 asyncio task 并发表达式求值。"
            ),
            Symbol("perform"): EffectOperator("perform", _special_effect_form, "执行 effect。"),
            Symbol("py"): EffectOperator(
                "py", _py, "执行内嵌 async Python，并用 keyword 参数绑定值。"
            ),
            Symbol("quote"): MetaOperator("quote", _quote, "返回一个表达式，不求值。"),
            Symbol("resume"): EffectOperator(
                "resume", _special_effect_form, "恢复捕获的 effect continuation。"
            ),
            Symbol("set"): PureOperator("set", _set, "构造 set。", _evaluate_data_args),
            Symbol("set?"): PureOperator("set?", _set_predicate, "判断值是否为 set。"),
            Symbol("spawn"): EffectOperator("spawn", _spawn, "创建 asyncio task。"),
            Symbol("handle"): ControlOperator(
                "handle", _special_effect_form, "处理表达式产生的 effect。"
            ),
            Symbol("tuple"): PureOperator("tuple", _tuple, "构造 tuple。", _evaluate_data_args),
            Symbol("tuple?"): PureOperator("tuple?", _tuple_predicate, "判断值是否为 tuple。"),
            Symbol("assert-failed"): EffectDefinition(
                Symbol("assert-failed"),
                resumable=False,
                doc="assert 失败产生的不可恢复 effect。",
            ),
            Symbol("python-error"): EffectDefinition(
                Symbol("python-error"),
                resumable=False,
                doc="py 宿主边界传播的 Python 异常 effect。",
            ),
        },
    )


def _ensure_number(value: object) -> int | float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise QyTypeError(f"expected number, got {value!r}", metadata={"value": value})
    return value


def _ensure_tuple(value: object) -> tuple[object, ...]:
    if not isinstance(value, tuple):
        raise QyTypeError(
            f"expected tuple, got {value!r}",
            span=get_span(value),
            metadata={"value": value},
        )
    return value


def _ensure_sequence(value: object) -> tuple[object, ...] | list[object]:
    if isinstance(value, list):
        return cast(list[object], value)
    if not isinstance(value, tuple):
        raise QyTypeError(
            f"expected tuple or list, got {value!r}",
            span=get_span(value),
            metadata={"value": value},
        )
    return value


def _ensure_index(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise QyTypeError(
            f"expected integer index, got {value!r}",
            span=get_span(value),
            metadata={"value": value},
        )
    return value


def _truthy(value: object) -> bool:
    return value is not False and value is not None and value != () and value is not QY_EMPTY_LIST


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
    name = ensure_symbol(name, "macro name")
    param_symbols = _ensure_parameter_list(params, "macro")
    macro = MacroDefinition(name, param_symbols, tuple(body), env)
    return env.define(name, macro)


def _atom(value: object) -> bool:
    if value is QY_EMPTY_LIST:
        return True
    if isinstance(value, QyCons):
        return False
    return not isinstance(value, tuple) or len(value) == 0


def _eq(left: object, right: object) -> bool:
    if left is QY_EMPTY_LIST or right is QY_EMPTY_LIST:
        return left is QY_EMPTY_LIST and right is QY_EMPTY_LIST
    if isinstance(left, QyCons) or isinstance(right, QyCons):
        return left is right
    if isinstance(left, tuple) and isinstance(right, tuple):
        return len(left) == 0 and len(right) == 0
    return left == right


def _car(value: object) -> object:
    if isinstance(value, QyCons):
        return value.head
    if value is QY_EMPTY_LIST:
        raise QyArityError("car expects a non-empty cons, tuple, or list")
    items = _ensure_sequence(value)
    if not items:
        raise QyArityError("car expects a non-empty cons, tuple, or list")
    return items[0]


def _cdr(value: object) -> object:
    if isinstance(value, QyCons):
        return value.tail
    if value is QY_EMPTY_LIST:
        raise QyArityError("cdr expects a non-empty cons, tuple, or list")
    items = _ensure_sequence(value)
    if not items:
        raise QyArityError("cdr expects a non-empty cons, tuple, or list")
    if isinstance(items, list):
        return list(items[1:])
    return items[1:]


def _cons(head: object, tail: object) -> object:
    if tail is QY_EMPTY_LIST or isinstance(tail, QyCons):
        return QyCons(head, tail)
    if isinstance(tail, list):
        return [head, *tail]
    if isinstance(tail, tuple):
        return (head, *tail)
    return QyCons(head, tail)


def _tuple(*args: object) -> tuple[object, ...]:
    return tuple(args)


def _list(*args: object) -> list[object]:
    return list(args)


def _dict(*args: object) -> dict[object, object]:
    if len(args) % 2 != 0:
        raise QyArityError(
            f"dict expects key/value pairs, got {len(args)} argument(s)",
            metadata={"actual": len(args)},
        )
    result: dict[object, object] = {}
    for index in range(0, len(args), 2):
        key = args[index]
        value = args[index + 1]
        try:
            result[key] = value
        except TypeError as e:
            raise QyTypeError(
                f"dict key must be hashable, got {key!r}",
                span=get_span(key),
                cause=e,
                metadata={"key": key},
            ) from e
    return result


def _set(*args: object) -> set[object]:
    result: set[object] = set()
    for value in args:
        try:
            result.add(value)
        except TypeError as e:
            raise QyTypeError(
                f"set item must be hashable, got {value!r}",
                span=get_span(value),
                cause=e,
                metadata={"value": value},
            ) from e
    return result


def _tuple_predicate(value: object) -> bool:
    return isinstance(value, tuple)


def _list_predicate(value: object) -> bool:
    return isinstance(value, list)


def _dict_predicate(value: object) -> bool:
    return isinstance(value, dict)


def _set_predicate(value: object) -> bool:
    return isinstance(value, set)


def _len(value: object) -> int:
    if isinstance(value, Symbol):
        return len(value.name)
    if value is QY_EMPTY_LIST:
        return 0
    if isinstance(value, QyCons):
        try:
            return len(qy_cons_to_tuple(value))
        except TypeError as e:
            raise QyTypeError("len expects a proper Qy cons list", cause=e) from e
    if isinstance(value, str | tuple | list | dict | set):
        return len(value)
    raise QyTypeError(
        f"len expects a collection, got {value!r}",
        span=get_span(value),
        metadata={"value": value},
    )


def _get(collection: object, key: object, *default_values: object) -> object:
    if len(default_values) > 1:
        raise QyArityError(
            f"get expects two or three arguments, got {len(default_values) + 2}",
            metadata={"expected": "2..3", "actual": len(default_values) + 2},
        )
    default = default_values[0] if default_values else None
    if isinstance(collection, dict):
        mapping = cast(dict[object, object], collection)
        try:
            return mapping[key]
        except (KeyError, TypeError):
            return default
    if isinstance(collection, tuple | list):
        index = _ensure_index(key)
        try:
            return collection[index]
        except IndexError:
            return default
    if collection is QY_EMPTY_LIST:
        return default
    if isinstance(collection, QyCons):
        index = _ensure_index(key)
        try:
            return qy_cons_to_tuple(collection)[index]
        except (IndexError, TypeError):
            return default
    raise QyTypeError(
        f"get expects a cons, tuple, list, or dict, got {collection!r}",
        span=get_span(collection),
        metadata={"collection": collection},
    )


def _has(*args: object) -> bool:
    if len(args) != 2:
        raise QyArityError(
            f"has? expects exactly two arguments, got {len(args)}",
            metadata={"expected": 2, "actual": len(args)},
        )
    collection, key = args
    if isinstance(collection, dict):
        try:
            return key in collection
        except TypeError:
            return False
    if isinstance(collection, set):
        try:
            return key in collection
        except TypeError:
            return False
    if isinstance(collection, tuple | list):
        index = _ensure_index(key)
        return -len(collection) <= index < len(collection)
    if collection is QY_EMPTY_LIST:
        return False
    if isinstance(collection, QyCons):
        index = _ensure_index(key)
        try:
            length = len(qy_cons_to_tuple(collection))
        except TypeError:
            return False
        return -length <= index < length
    raise QyTypeError(
        f"has? expects a cons, tuple, list, dict, or set, got {collection!r}",
        span=get_span(collection),
        metadata={"collection": collection},
    )


async def _evaluate_data_args(args: tuple[object, ...], env: Environment) -> tuple[object, ...]:
    return tuple([await _evaluate_data_arg(arg, env) for arg in args])


async def _evaluate_lookup_args(args: tuple[object, ...], env: Environment) -> tuple[object, ...]:
    if not args:
        return ()
    collection = await evaluate_async(args[0], env)
    rest = tuple([await _evaluate_data_arg(arg, env) for arg in args[1:]])
    return (collection, *rest)


async def _evaluate_data_arg(expression: object, env: Environment) -> object:
    try:
        return await evaluate_async(expression, env)
    except EvaluationError:
        if isinstance(expression, Symbol):
            return expression
        raise


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
    component = ComponentDefinition(name, param_symbols, tuple(body), env)
    return env.define(name, component)


def _defeffect(args: tuple[object, ...], env: Environment) -> object:
    if not args:
        raise QyArityError("defeffect expects an effect name")

    name, *options = args
    name = ensure_symbol(name, "defeffect name")
    resumable = _parse_defeffect_resumable(tuple(options))
    effect = EffectDefinition(name, resumable=resumable)
    return env.define(name, effect)


def _parse_defeffect_resumable(options: tuple[object, ...]) -> bool:
    if not options:
        return True
    if len(options) != 2 or options[0] != Symbol(":resumable"):
        raise QyTypeError(
            "defeffect options must be empty or :resumable true|false",
            span=get_span(options[0]) if options else None,
        )
    value = options[1]
    if value == Symbol("true"):
        return True
    if value == Symbol("false"):
        return False
    raise QyTypeError(
        f"defeffect :resumable expects true or false, got {value!r}",
        span=get_span(value),
    )


def _special_effect_form(args: tuple[object, ...], env: Environment) -> object:
    del args, env
    raise QyRuntimeError("effect special forms are handled by the evaluator")


async def _module(args: tuple[object, ...], env: Environment) -> object:
    if not args:
        raise QyArityError("module expects a name and body")

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
    results = await asyncio.gather(*tasks, return_exceptions=True)
    errors = tuple(
        _exception_to_qy_error(result) for result in results if isinstance(result, BaseException)
    )
    if errors:
        raise QyAggregateError(
            f"parallel failed with {len(errors)} error(s)",
            errors=errors,
        )
    return tuple(results)


async def _cache(args: tuple[object, ...], env: Environment) -> object:
    if len(args) != 1:
        raise QyArityError(
            f"cache expects exactly one argument, got {len(args)}",
            metadata={"expected": 1, "actual": len(args)},
        )

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
        raise QyArityError(
            f"spawn expects exactly one argument, got {len(args)}",
            metadata={"expected": 1, "actual": len(args)},
        )
    return asyncio.create_task(evaluate_async(args[0], env))


async def _await(args: tuple[object, ...], env: Environment) -> object:
    if not args:
        raise QyArityError("await expects at least one argument")

    values: list[object] = []
    for arg in args:
        value = await evaluate_async(arg, env)
        values.append(await _await_cached_value(value))

    if len(values) == 1:
        return values[0]
    return tuple(values)


async def _py(args: tuple[object, ...], env: Environment) -> object:
    if not args:
        raise QyArityError("py expects Python source and optional keyword arguments")

    source = await _evaluate_py_source(args[0], env)
    bindings = await _evaluate_py_bindings(args[1:], env)
    parameter_names = tuple(bindings)
    function = _compile_py_function(source, parameter_names)
    try:
        result = await function(**bindings)
        result = await _await_py_result(result)
        return _python_to_qy(result)
    except QyError:
        raise
    except asyncio.CancelledError as e:
        raise QyCancelledError("py execution cancelled", span=get_span(args[0]), cause=e) from e
    except Exception as e:
        python_error = QyPythonError(
            f"Python error in py: {e}",
            span=get_span(args[0]),
            cause=e,
            metadata={"python_exception": type(e).__name__},
        )
        raise QyEffectSignal(
            "python-error",
            python_error,
            _non_resumable_python_continuation(),
            resumable=False,
            span=get_span(args[0]),
            cause=python_error,
        ) from e


async def _evaluate_py_source(expression: object, env: Environment) -> str:
    if isinstance(expression, Symbol):
        try:
            value = await evaluate_async(expression, env)
        except EvaluationError:
            return expression.name
    else:
        value = await evaluate_async(expression, env)

    if isinstance(value, Symbol):
        return value.name
    if isinstance(value, str):
        return value
    raise QyTypeError(
        f"py source must be text, got {value!r}",
        span=get_span(expression),
        metadata={"value": value},
    )


async def _evaluate_py_bindings(args: tuple[object, ...], env: Environment) -> dict[str, object]:
    if len(args) % 2 != 0:
        raise QyArityError("py keyword arguments must be :name value pairs")

    bindings: dict[str, object] = {}
    for index in range(0, len(args), 2):
        name = _py_parameter_name(args[index])
        if name in bindings:
            raise QyArityError(
                f"py got duplicate parameter {name!r}",
                span=get_span(args[index]),
                metadata={"parameter": name},
            )
        value = await _evaluate_py_value(args[index + 1], env)
        bindings[name] = _qy_to_python(value, env)
    return bindings


async def _evaluate_py_value(expression: object, env: Environment) -> object:
    if isinstance(expression, Symbol):
        try:
            return await evaluate_async(expression, env)
        except EvaluationError:
            return expression
    return await evaluate_async(expression, env)


def _py_parameter_name(value: object) -> str:
    if not isinstance(value, Symbol) or not value.name.startswith(":"):
        raise QyTypeError(
            f"py keyword name must be a :keyword symbol, got {value!r}",
            span=get_span(value),
            metadata={"value": value},
        )

    name = value.name[1:].replace("-", "_")
    if not name.isidentifier() or keyword.iskeyword(name):
        raise QyTypeError(
            f"py keyword {value.name!r} is not a valid Python identifier",
            span=value.span,
            metadata={"keyword": value.name},
        )
    return name


def _compile_py_function(
    source: str, parameter_names: tuple[str, ...]
) -> Callable[..., Awaitable[object]]:
    normalized_source = textwrap.dedent(source).strip("\n")
    cache_key = (normalized_source, parameter_names)
    try:
        return _PY_FUNCTION_CACHE[cache_key]
    except KeyError:
        pass

    function_source = _build_py_function_source(normalized_source, parameter_names)
    filename = _py_filename(normalized_source, parameter_names)
    linecache.cache[filename] = (
        len(function_source),
        None,
        function_source.splitlines(keepends=True),
        filename,
    )
    globals_ = {
        "__builtins__": vars(builtins),
        "__name__": "__qy_py__",
        "asyncio": asyncio,
    }
    namespace: dict[str, object] = {}
    try:
        code = compile(function_source, filename, "exec")
        exec(code, globals_, namespace)
    except SyntaxError as e:
        raise QyPythonError(_format_py_syntax_error(e), cause=e) from e

    function = namespace[_PY_FUNCTION_NAME]
    if not callable(function):
        raise QyRuntimeError("py failed to compile a callable async function")
    compiled_function = cast(Callable[..., Awaitable[object]], function)
    _PY_FUNCTION_CACHE[cache_key] = compiled_function
    return compiled_function


def _build_py_function_source(source: str, parameter_names: tuple[str, ...]) -> str:
    parameters = ", ".join(parameter_names)
    body = source if source.strip() else "pass"
    return f"async def {_PY_FUNCTION_NAME}({parameters}):\n{textwrap.indent(body, '    ')}\n"


def _py_filename(source: str, parameter_names: tuple[str, ...]) -> str:
    digest_source = f"{parameter_names!r}\n{source}".encode()
    digest = hashlib.sha256(digest_source).hexdigest()[:12]
    return f"<qy-py {digest}>"


def _format_py_syntax_error(error: SyntaxError) -> str:
    line = error.lineno
    if line is not None and line > 1:
        line -= 1
    location = f" at line {line}" if line is not None else ""
    return f"py compile error{location}: {error.msg}"


async def _await_py_result(value: object) -> object:
    while inspect.isawaitable(value):
        value = await value
    return value


def _qy_to_python(value: object, env: Environment) -> object:
    if isinstance(value, HostObjectRef):
        return value.value
    if value is QY_EMPTY_LIST:
        return QY_EMPTY_LIST
    if isinstance(value, QyCons):
        return map_qy_cons(value, lambda item: _qy_to_python(item, env))
    if _is_qy_callable(value):
        return _wrap_qy_callable(value, env)
    if isinstance(value, Symbol):
        return _symbol_to_python(value)
    if isinstance(value, tuple):
        return tuple(_qy_to_python(item, env) for item in value)
    if isinstance(value, list):
        return [_qy_to_python(item, env) for item in value]
    if isinstance(value, dict):
        return {_qy_to_python(key, env): _qy_to_python(item, env) for key, item in value.items()}
    if isinstance(value, set):
        return {_qy_to_python(item, env) for item in value}
    return value


def _symbol_to_python(value: Symbol) -> object:
    if value.name == "true":
        return True
    if value.name == "false":
        return False
    if value.name == "nil":
        return None
    try:
        return int(value.name)
    except ValueError:
        pass
    try:
        return float(value.name)
    except ValueError:
        pass
    return value.name


def _python_to_qy(value: object) -> object:
    if value is QY_EMPTY_LIST:
        return QY_EMPTY_LIST
    if isinstance(value, QyCons):
        return map_qy_cons(value, _python_to_qy)
    if isinstance(value, HostObjectRef | Symbol):
        return value
    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, str):
        return Symbol(value)
    if isinstance(value, list):
        return [_python_to_qy(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_python_to_qy(item) for item in value)
    if isinstance(value, dict):
        return {_python_to_qy(key): _python_to_qy(item) for key, item in value.items()}
    if isinstance(value, set):
        return {_python_to_qy(item) for item in value}
    return HostObjectRef(value)


def _is_qy_callable(value: object) -> bool:
    return isinstance(
        value,
        PureOperator
        | ScopeOperator
        | ControlOperator
        | EffectOperator
        | MetaOperator
        | MacroDefinition
        | UserFunction
        | ComponentDefinition,
    )


def _wrap_qy_callable(value: object, env: Environment) -> Callable[..., object]:
    async def qy_callable(*args: object, **kwargs: object) -> object:
        if kwargs:
            raise QyTypeError("Qy callable wrappers do not accept Python keyword arguments")
        qy_args = tuple(_python_to_qy(arg) for arg in args)
        result = await _call_qy_callable(value, qy_args, env)
        return _qy_to_python(result, env)

    if (name := _qy_callable_name(value)) is not None:
        qy_callable.__name__ = name
    return qy_callable


def _qy_callable_name(value: object) -> str | None:
    if isinstance(
        value, PureOperator | ScopeOperator | ControlOperator | EffectOperator | MetaOperator
    ):
        return value.name
    if isinstance(value, MacroDefinition | UserFunction | ComponentDefinition):
        return value.name.name
    return None


async def _call_qy_callable(value: object, args: tuple[object, ...], env: Environment) -> object:
    if isinstance(value, PureOperator):
        return await _await_cached_value(value(*args))
    if isinstance(value, UserFunction | ComponentDefinition):
        return await _await_cached_value(value(*args))
    if isinstance(value, ScopeOperator | ControlOperator | EffectOperator):
        return await _await_cached_value(value(args, env))
    if isinstance(value, MacroDefinition):
        expanded = await value.expand(args)
        return await evaluate_async(expanded, env)
    if isinstance(value, MetaOperator):
        return await _await_cached_value(value((Symbol(value.name), *args), env))
    raise QyTypeError(f"{value!r} is not a Qy callable")


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


def _exception_to_qy_error(error: BaseException) -> QyError:
    if isinstance(error, QyError):
        return error
    if isinstance(error, asyncio.CancelledError):
        return QyCancelledError("task cancelled", cause=error)
    return QyRuntimeError(
        str(error),
        cause=error,
        metadata={"python_exception": type(error).__name__},
    )


def _non_resumable_python_continuation() -> QyContinuation:
    async def resume(value: object) -> object:
        return value

    return QyContinuation("python-error", False, resume)
