# coding: utf-8
"""WebAssembly backend ABI.

值编码（i64，低 3 位 tag）：

- ``tag 0`` int：``(value << 3) | 0``（61-bit signed）
- ``tag 1`` nil：常量 ``1``
- ``tag 2`` T：常量 ``2``
- ``tag 3`` char：``(codepoint << 3) | 3``
- ``tag 4`` callable：``(table_index << 3) | 4``
- ``tag 5`` string：``(data_offset << 3) | 5``（UTF-8 存于 linear memory）

调用约定：所有可调用目标共享 wasm 类型 ``(param i32 i32) (result i64)``
（``argc``, ``argv``），``argv`` 指向 linear memory 中连续的 i64 参数区。
函数表布局：``[0, NUM_BUILTINS)`` 是内建算子 trampoline，之后是编译出的
Qy 函数（``table_index == NUM_BUILTINS + fn_idx``）。
"""

from __future__ import annotations

__all__ = [
    "BUILTIN_NAMES",
    "NUM_BUILTINS",
    "TAG_CALLABLE",
    "TAG_CHAR",
    "TAG_INT",
    "TAG_NIL",
    "TAG_STRING",
    "TAG_T",
    "VAL_NIL",
    "VAL_T",
    "builtin_index",
    "callable_value",
    "char_value",
    "int_value",
    "string_value",
    "table_index_for_function",
]

# 与 qy/backend/llvm/abi.py 的 BUILTIN_NAMES 顺序保持一致。
BUILTIN_NAMES: list[str] = [
    "+",
    "-",
    "*",
    "/",
    "=",
    "eq",
    "<",
    ">",
    "display",
    "echo",
    "newline",
    "read",
    "read-int",
    "cons",
    "car",
    "cdr",
    "nil?",
    "not",
]
NUM_BUILTINS: int = len(BUILTIN_NAMES)

TAG_INT = 0
TAG_NIL = 1
TAG_T = 2
TAG_CHAR = 3
TAG_CALLABLE = 4
TAG_STRING = 5

VAL_NIL = TAG_NIL
VAL_T = TAG_T


def builtin_index(name: str) -> int:
    """Return the table index of a builtin, or -1 if not a builtin."""
    try:
        return BUILTIN_NAMES.index(name)
    except ValueError:
        return -1


def int_value(value: int) -> int:
    """Encode a Python int as a tagged wasm i64."""
    return (value << 3) | TAG_INT


def char_value(codepoint: int) -> int:
    return (codepoint << 3) | TAG_CHAR


def string_value(data_offset: int) -> int:
    return (data_offset << 3) | TAG_STRING


def table_index_for_function(fn_idx: int) -> int:
    return NUM_BUILTINS + fn_idx


def callable_value(table_index: int) -> int:
    return (table_index << 3) | TAG_CALLABLE
