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
from qy.reader import Symbol
from qy.reader import get_span
from qy.stdlib.imports import parse_from_import
from qy.stdlib.module import StandardModule

_PY_FUNCTION_NAME = "__qy_py__"
_PY_FUNCTION_CACHE: dict[tuple[str, tuple[str, ...]], Callable[..., Awaitable[object]]] = {}


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
            Symbol("defeffect"): ScopeOperator(
                "defeffect", _defeffect, "Declare an effect for perform/handle analysis."
            ),
            Symbol("defun"): ScopeOperator(
                "defun", _defun, "Define a function in the current environment."
            ),
            Symbol("eq"): PureOperator("eq", _eq, "Compare atoms and empty lists."),
            Symbol("eval"): MetaOperator("eval", _eval, "Evaluate one symbolic form."),
            Symbol("from"): ScopeOperator(
                "from", _from_import, "Import standard module operators into the current scope."
            ),
            Symbol("lambda"): ScopeOperator("lambda", _lambda, "Create an anonymous function."),
            Symbol("let"): ScopeOperator("let", _let, "Evaluate a body in a local lexical scope."),
            Symbol("macro"): MetaOperator(
                "macro", _macro, "Define a macro that expands unevaluated forms."
            ),
            Symbol("module"): ScopeOperator("module", _module, "Define and register a module."),
            Symbol("parallel"): EffectOperator(
                "parallel", _parallel, "Evaluate expressions concurrently with asyncio tasks."
            ),
            Symbol("perform"): EffectOperator(
                "perform", _special_effect_form, "Perform an effect."
            ),
            Symbol("py"): EffectOperator(
                "py", _py, "Execute embedded async Python with keyword-bound values."
            ),
            Symbol("quote"): MetaOperator(
                "quote", _quote, "Return one expression without evaluating it."
            ),
            Symbol("resume"): EffectOperator(
                "resume", _special_effect_form, "Resume a captured effect continuation."
            ),
            Symbol("spawn"): EffectOperator("spawn", _spawn, "Create an asyncio task."),
            Symbol("handle"): ControlOperator(
                "handle", _special_effect_form, "Handle effects from an expression."
            ),
            Symbol("python-error"): EffectDefinition(
                Symbol("python-error"),
                resumable=False,
                doc="Python exception raised across the py host boundary.",
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
        raise QyArityError("quote expects exactly one argument", span=get_span(expression))
    return args[0]


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
    return not isinstance(value, tuple) or len(value) == 0


def _eq(left: object, right: object) -> bool:
    if isinstance(left, tuple) and isinstance(right, tuple):
        return len(left) == 0 and len(right) == 0
    return left == right


def _car(value: object) -> object:
    items = _ensure_tuple(value)
    if not items:
        raise QyArityError("car expects a non-empty tuple")
    return items[0]


def _cdr(value: object) -> tuple[object, ...]:
    items = _ensure_tuple(value)
    if not items:
        raise QyArityError("cdr expects a non-empty tuple")
    return items[1:]


def _cons(head: object, tail: object) -> tuple[object, ...]:
    return (head, *_ensure_tuple(tail))


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
    if isinstance(value, HostObjectRef | Symbol):
        return value
    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, str):
        return Symbol(value)
    if isinstance(value, list | tuple):
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
