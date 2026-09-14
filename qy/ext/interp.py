# coding: utf-8
"""``qy.ext.interp``：meta-circular 解释器 / 语言工具链的宿主支持扩展。.

自举解释器需要少量通用宿主能力：读取 CLI 参数、按名解析宿主模块导出、
按 Qy display 规则格式化、抛出语言级错误、生成全新 symbol。它们不属于
测试基础设施，因此单独声明扩展，避免解释器依赖测试扩展。

capability:
- ``cli``：读取进程 CLI 参数
- ``introspection``：解析宿主模块导出（自举解释器的 from 实现）
- ``symbols``：生成全新 symbol（宏 hygiene / gensym）
"""

from __future__ import annotations

import itertools

from qy.core.operators import ScopeOperator
from qy.core.syntax import list_to_chain
from qy.core.syntax import nil as QY_NIL
from qy.errors import EvaluationError
from qy.ext.descriptor import ExtensionBinding
from qy.ext.descriptor import ExtensionCapability
from qy.ext.descriptor import ExtensionDescriptor
from qy.ext.registry import register_extension
from qy.frontend.reader import Symbol
from qy.import_.module import StandardModule
from qy.session.runtime_space import RuntimeSpace as Environment

__all__ = ["DESCRIPTOR", "module", "set_cli_args"]

_CLI_ARGS_CACHE_KEY = ("qy", "cli_args")
_GENSYM_COUNTER = itertools.count(1)


def _as_text(value: object) -> str:
    if isinstance(value, Symbol):
        return value.name
    return str(value)


def set_cli_args(env: Environment, args: tuple[str, ...]) -> None:
    """由 CLI 注入进程参数（自举解释器通过 ``cli-args`` 读取）。."""
    env.cache_define(_CLI_ARGS_CACHE_KEY, tuple(args))


def _cli_args(args: tuple[object, ...], env: Environment) -> object:
    if args:
        return list_to_chain(())
    try:
        cached_args = env.cache_lookup(_CLI_ARGS_CACHE_KEY)
    except KeyError:
        cached_args = ()
    if not isinstance(cached_args, tuple):
        return list_to_chain(())
    normalized = tuple(item for item in cached_args if isinstance(item, str))
    return list_to_chain(Symbol(item) for item in normalized)


def _lookup_export(args: tuple[object, ...], env: Environment) -> object:
    del env
    if len(args) != 2:
        return QY_NIL
    module_name = _as_text(args[0])
    export_name = _as_text(args[1])
    try:
        from qy.import_.registry import load_module

        module = load_module(module_name)
    except Exception:
        return QY_NIL
    return module.exports.get(Symbol(export_name), QY_NIL)


def _display(args: tuple[object, ...], env: Environment) -> object:
    del env
    if len(args) != 1:
        return QY_NIL
    from qy.display import format_value
    from qy.sem.core import StringValue

    return StringValue(format_value(args[0]))


def _raise_error(args: tuple[object, ...], env: Environment) -> object:
    del env
    from qy.display import format_value

    message = " ".join(format_value(arg) for arg in args) if args else "error"
    raise EvaluationError(message)


def _gensym(args: tuple[object, ...], env: Environment) -> object:
    del env
    prefix = _as_text(args[0]) if args else "g"
    return Symbol(f"__qy_meta_gensym_{prefix}_{next(_GENSYM_COUNTER)}")


def module() -> StandardModule:
    return StandardModule(
        "qy.ext.interp",
        {
            Symbol("cli-args"): ScopeOperator(
                "cli-args", _cli_args, "读取 CLI 传入的额外参数（chain of symbol）。"
            ),
            Symbol("lookup-export"): ScopeOperator(
                "lookup-export",
                _lookup_export,
                "按 (模块名 导出名) 解析宿主模块导出；用于自举解释器的 from 实现。",
            ),
            Symbol("display"): ScopeOperator(
                "display",
                _display,
                "按 Qy display 规则把值格式化为 string；不做 literal 解析，不打印。",
            ),
            Symbol("raise-error"): ScopeOperator(
                "raise-error",
                _raise_error,
                "以 EvaluationError 终止当前求值；供自举解释器报告未处理效应等错误。",
            ),
            Symbol("gensym"): ScopeOperator(
                "gensym",
                _gensym,
                "用宿主计数器生成全新 symbol；供自举解释器实现宏 hygiene。",
            ),
        },
    )


def _bindings() -> tuple[ExtensionBinding, ...]:
    def binding(name: str, doc: str, capability: str) -> ExtensionBinding:
        return ExtensionBinding(name, kind="scope", doc=doc, capabilities=(capability,))

    return (
        binding("cli-args", "读取 CLI 传入的额外参数。", "cli"),
        binding("lookup-export", "解析宿主模块导出。", "introspection"),
        binding("display", "按 Qy display 规则格式化值。", "introspection"),
        binding("raise-error", "以语言级错误终止求值。", "introspection"),
        binding("gensym", "生成全新 symbol。", "symbols"),
    )


DESCRIPTOR = ExtensionDescriptor(
    name="qy.ext.interp",
    module_name="qy.ext.interp",
    version="0.1",
    description="meta-circular 解释器 / 工具链的宿主支持扩展。",
    capabilities=(
        ExtensionCapability("cli", "读取进程 CLI 参数"),
        ExtensionCapability("introspection", "解析宿主模块导出与值格式化"),
        ExtensionCapability("symbols", "生成全新 symbol"),
    ),
    bindings=_bindings(),
)

register_extension(DESCRIPTOR, module)
