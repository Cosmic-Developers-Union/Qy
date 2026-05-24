# coding: utf-8

from __future__ import annotations

import asyncio
import builtins
import hashlib
import inspect
import keyword
import linecache
import textwrap
from collections.abc import Awaitable
from collections.abc import Callable
from typing import cast

from qy.core.operators import ControlOperator
from qy.core.operators import EffectOperator
from qy.core.operators import MetaOperator
from qy.core.operators import PureOperator
from qy.core.operators import ScopeOperator
from qy.environment import Environment
from qy.errors import QyArityError
from qy.errors import QyCancelledError
from qy.errors import QyEffectSignal
from qy.errors import QyError
from qy.errors import QyPythonError
from qy.errors import QyRuntimeError
from qy.errors import QyTypeError
from qy.frontend.reader import Symbol
from qy.frontend.reader import get_span
from qy.macro import MacroDefinition
from qy.sem.runtime import UserFunction
from qy.std.data import python_container_operators
from qy.std.effects import _await_cached_value
from qy.values import QY_NIL
from qy.values import QY_T
from qy.values import QyCons
from qy.values import map_qy_cons
from qy.vm.instance.frame import QyContinuation
from qy.vm.instance.machine import evaluate_form_async as evaluate_async
from qy.vm.instance.values import HostObjectRef

_PY_FUNCTION_NAME = "__qy_py__"
_PY_FUNCTION_CACHE: dict[tuple[str, tuple[str, ...]], Callable[..., Awaitable[object]]] = {}


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
            value = env.resolve(expression)
        except Exception:
            return expression.name
    else:
        value = expression

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
            return env.resolve(expression)
        except Exception:
            return expression
    return expression


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


class _ChainWrapperMeta(type):
    """Metaclass to make _ChainWrapper report its name as 'QyChain'."""

    @property
    def __name__(cls) -> str:
        return "QyChain"


class _ChainWrapper(metaclass=_ChainWrapperMeta):
    """Wrapper for AST Chain that makes it iterable in Python while preserving type."""

    def __init__(self, chain: object, env: Environment) -> None:
        from qy.core.syntax import chain_to_list

        self.chain = chain
        self._items = chain_to_list(chain)
        self._env = env

    def __iter__(self):

        # Convert symbols to Python values when iterating
        for item in self._items:
            yield _qy_to_python(item, self._env)

    def __repr__(self) -> str:
        return f"QyChain({self.chain!r})"


def _qy_to_python(value: object, env: Environment) -> object:
    from qy.core.syntax import Chain
    from qy.core.syntax import is_chain

    if isinstance(value, HostObjectRef):
        return value.value
    if value is QY_NIL or value is QY_T:
        return value
    # Handle AST Chain (from quote) - keep as Chain but convert elements
    if isinstance(value, Chain) or is_chain(value):
        # Return a wrapper that makes Chain iterable in Python
        return _ChainWrapper(value, env)
    # Handle runtime QyCons
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
    if value is QY_NIL or value is QY_T:
        return value
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
    from qy.vm.bytecode import BytecodeFunctionValue

    return isinstance(
        value,
        PureOperator
        | ScopeOperator
        | ControlOperator
        | EffectOperator
        | MetaOperator
        | MacroDefinition
        | UserFunction
        | BytecodeFunctionValue,
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
    from qy.vm.bytecode import BytecodeFunctionValue

    if isinstance(
        value, PureOperator | ScopeOperator | ControlOperator | EffectOperator | MetaOperator
    ):
        return value.name
    if isinstance(value, MacroDefinition | UserFunction):
        return value.name.name
    if isinstance(value, BytecodeFunctionValue):
        return value.function.name.name
    return None


async def _call_qy_callable(value: object, args: tuple[object, ...], env: Environment) -> object:
    from qy.vm.bytecode import BytecodeFunctionValue

    if isinstance(value, PureOperator):
        return await _await_cached_value(value(*args))
    if isinstance(value, UserFunction):
        return await _await_cached_value(value(*args))
    if isinstance(value, BytecodeFunctionValue):
        from qy.vm.instance.machine import call_function_value

        return await call_function_value(value, args, env)
    if isinstance(value, ScopeOperator | ControlOperator | EffectOperator):
        return await _await_cached_value(value(args, env))
    if isinstance(value, MacroDefinition):
        expanded = await value.expand(args)
        return await evaluate_async(expanded, env)
    if isinstance(value, MetaOperator):
        return await _await_cached_value(value((Symbol(value.name), *args), env))
    raise QyTypeError(f"{value!r} is not a Qy callable")


def _non_resumable_python_continuation() -> QyContinuation:
    async def resume(value: object) -> object:
        return value

    return QyContinuation("python-error", False, resume)


def operators() -> dict[Symbol, object]:
    return {
        Symbol("py"): EffectOperator("py", _py, "执行内嵌 async Python，并用 keyword 参数绑定值。"),
        **python_container_operators(),
    }
