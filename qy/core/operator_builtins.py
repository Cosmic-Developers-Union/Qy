# coding: utf-8
"""内建算子表（backend builtin ABI 的唯一事实源）。.

Qy 的"内建算子"指可以被后端直接调用、不必经过 symbol-space 查找与 Python 算子对象的
那批算子。它们的**名字、ABI 参数个数、下标顺序**必须对所有后端一致：

- ``qy/backend/wasm/abi.py`` 由此派生 ``BUILTIN_NAMES`` / ``builtin_index``；
- ``qy/backend/llvm/abi.py`` 由此派生 ``BUILTIN_OPS`` / ``BUILTIN_NAMES``；
- wasm 宿主 runtime（``qy/resources/wasm/runtime.js`` 的 ``const builtins``）按同一
  下标顺序实现，``tests/test_operator_builtins.py`` 会解析该文件核对顺序。

在此之前这些表在三个地方各写一份、靠注释提醒手工同步；现在只有本模块是事实源。

禁止：
- 不得在这里放宿主实现（JS / C 运行时各自实现自己的 body）；
- 不得改变既有顺序（它是跨后端 ABI：调序等于破坏已编译产物与宿主 runtime）。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

__all__ = [
    "BUILTIN_INDEX",
    "BUILTIN_NAMES",
    "BUILTIN_OPERATORS",
    "LANGUAGE_IMPLEMENTATION_MODULES",
    "NUM_BUILTINS",
    "BuiltinOperator",
    "builtin_index",
    "builtin_operator",
    "is_language_implementation_operator",
]


@dataclass(frozen=True, slots=True)
class BuiltinOperator:
    """一个内建算子在 ABI 上的声明。.

    - ``name``：Qy 符号名；
    - ``arity``：内建调用接受的参数个数（固定元数快路径，不是该算子的全部元数）；
    - ``runtime_symbol``：LLVM/宿主 runtime 侧入口名（wasm 由 JS runtime 按下标实现）。
    """

    name: str
    arity: int
    runtime_symbol: str


#: 顺序即 ABI 下标；与 qy/resources/wasm/runtime.js 的 builtins 数组顺序一致。
BUILTIN_OPERATORS: tuple[BuiltinOperator, ...] = (
    BuiltinOperator("+", 2, "mqr_add"),
    BuiltinOperator("-", 2, "mqr_sub"),
    BuiltinOperator("*", 2, "mqr_mul"),
    BuiltinOperator("/", 2, "mqr_div"),
    BuiltinOperator("=", 2, "mqr_eq"),
    BuiltinOperator("eq", 2, "mqr_eq"),
    BuiltinOperator("<", 2, "mqr_lt"),
    BuiltinOperator(">", 2, "mqr_gt"),
    BuiltinOperator("display", 1, "mqr_display"),
    BuiltinOperator("echo", 1, "mqr_echo"),
    BuiltinOperator("newline", 0, "mqr_newline"),
    BuiltinOperator("read", 0, "mqr_read"),
    BuiltinOperator("read-int", 0, "mqr_read_int"),
    BuiltinOperator("cons", 2, "mqr_cons"),
    BuiltinOperator("car", 1, "mqr_car"),
    BuiltinOperator("cdr", 1, "mqr_cdr"),
    BuiltinOperator("nil?", 1, "mqr_nil_p"),
    BuiltinOperator("not", 1, "mqr_not"),
)

BUILTIN_NAMES: tuple[str, ...] = tuple(operator.name for operator in BUILTIN_OPERATORS)

NUM_BUILTINS: int = len(BUILTIN_OPERATORS)

BUILTIN_INDEX: Mapping[str, int] = MappingProxyType(
    {operator.name: index for index, operator in enumerate(BUILTIN_OPERATORS)}
)


def builtin_index(name: str) -> int:
    """返回内建算子下标；不是内建算子时返回 -1。."""
    return BUILTIN_INDEX.get(name, -1)


def builtin_operator(name: str) -> BuiltinOperator | None:
    """返回内建算子声明；不是内建算子时返回 None。."""
    index = BUILTIN_INDEX.get(name)
    return None if index is None else BUILTIN_OPERATORS[index]


#: 语言实现自身的模块前缀。凡是"这个算子能不能在编译期求值 / 能不能降成内建调用"
#: 的判断都以它为准：宿主通过 ``register_pure`` 注入的算子（用户模块、``qy.ext.*``
#: 宿主桥）不在此列，因为它们的执行时机/副作用属于宿主。
LANGUAGE_IMPLEMENTATION_MODULES: tuple[str, ...] = ("qy.core.", "qy.session.", "qy.std.")


def is_language_implementation_operator(value: object) -> bool:
    """``value`` 是否是语言实现自身实现的算子（而非宿主注入/覆盖）。."""
    func = getattr(value, "func", None)
    module = getattr(func, "__module__", None)
    if not isinstance(module, str):
        return False
    return module.startswith(LANGUAGE_IMPLEMENTATION_MODULES)
