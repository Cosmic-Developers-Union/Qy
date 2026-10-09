# coding: utf-8
"""WebAssembly backend ABI.

值编码（i64，低 3 位 tag）：

- ``tag 0`` int：``(value << 3) | 0``（61-bit signed）
- ``tag 1`` nil：常量 ``1``
- ``tag 2`` T：常量 ``2``
- ``tag 3`` char：``(codepoint << 3) | 3``
- ``tag 4`` callable：``(table_index << 3) | 4``
- ``tag 5`` string：``(data_offset << 3) | 5``（UTF-8 存于 linear memory）
- ``tag 6`` float：``(data_offset << 3) | 6``（f64 存于 linear memory）
- ``tag 7`` heap：``(data_offset << 3) | 7``（linear memory 中的 heap 对象，首 i32 是子 tag：
  ``1`` symbol（``[i32 sub][i32 string_offset]``）、``2`` cons（``[i32 sub][i32 pad][i64 car][i64 cdr]``））

调用约定：所有可调用目标共享 wasm 类型 ``(param i32 i32) (result i64)``
（``argc``, ``argv``），``argv`` 指向 linear memory 中连续的 i64 参数区。
函数表布局：``[0, NUM_BUILTINS)`` 是内建算子 trampoline，之后是编译出的
Qy 函数（``table_index == NUM_BUILTINS + fn_idx``）。
"""

from __future__ import annotations

from qy.core.operator_builtins import BUILTIN_NAMES as CORE_BUILTIN_NAMES
from qy.core.operator_builtins import NUM_BUILTINS as NUM_CORE_BUILTINS
from qy.core.operator_builtins import builtin_index as _core_builtin_index

__all__ = [
    "BUILTIN_NAMES",
    "NUM_BUILTINS",
    "TAG_CALLABLE",
    "TAG_CHAR",
    "TAG_FLOAT",
    "TAG_HEAP",
    "TAG_INT",
    "TAG_NIL",
    "TAG_STRING",
    "TAG_T",
    "VAL_NIL",
    "VAL_T",
    "builtin_index",
    "callable_value",
    "char_value",
    "float_value",
    "heap_value",
    "int_value",
    "string_value",
    "table_index_for_function",
]

# 内建算子表的事实源在 qy/core/operator_builtins.py（顺序即 ABI 下标，与
# qy/resources/wasm/runtime.js 的 builtins 数组一致）。
BUILTIN_NAMES: tuple[str, ...] = CORE_BUILTIN_NAMES
NUM_BUILTINS: int = NUM_CORE_BUILTINS

TAG_INT = 0
TAG_NIL = 1
TAG_T = 2
TAG_CHAR = 3
TAG_CALLABLE = 4
TAG_STRING = 5
TAG_FLOAT = 6
TAG_HEAP = 7

#: heap 对象的子 tag（首 i32）。
HEAP_SYMBOL = 1
HEAP_CONS = 2

VAL_NIL = TAG_NIL
VAL_T = TAG_T


def builtin_index(name: str) -> int:
    """Return the ABI index of a builtin operator, or -1 when unknown."""
    return _core_builtin_index(name)


def int_value(value: int) -> int:
    """Encode a Python int as a tagged wasm i64."""
    return (value << 3) | TAG_INT


def char_value(codepoint: int) -> int:
    return (codepoint << 3) | TAG_CHAR


def string_value(data_offset: int) -> int:
    return (data_offset << 3) | TAG_STRING


def float_value(data_offset: int) -> int:
    return (data_offset << 3) | TAG_FLOAT


def heap_value(data_offset: int) -> int:
    return (data_offset << 3) | TAG_HEAP


def table_index_for_function(fn_idx: int) -> int:
    return NUM_BUILTINS + fn_idx


def callable_value(table_index: int) -> int:
    return (table_index << 3) | TAG_CALLABLE
