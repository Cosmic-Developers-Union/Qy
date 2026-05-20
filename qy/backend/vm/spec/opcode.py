# coding: utf-8
"""Opcode spec 目标模块。.

目标：
- 定义 opcode 集、operand schema、register effect、branch/effect 边界。
- 供 emitter、verifier、Python VM implementation、debug dump 共用。

当前：
- 从 qy/bytecode.py 迁移 opcode 定义和元数据。
- 提供 opcode 信息表，描述每个指令的操作数数量、是否有目标寄存器、是否是终结符、是否是分支。

禁止：
- 不得包含具体的执行逻辑。
- 不得依赖某个 Python VM instance。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

__all__ = [
    "OPCODE_TABLE",
    "Opcode",
    "OpcodeInfo",
]

Opcode = Literal[
    "APPEND_RESULT",
    "ALL_GATHER",
    "APPLY",
    "BUILD_TUPLE",
    "CACHE_EVAL",
    "CALL",
    "DEFEFFECT",
    "DEFINE_MODULE",
    "DEFINE_ONCE",
    "ENTER_SCOPE",
    "EXIT_SCOPE",
    "FROM_IMPORT",
    "HANDLE",
    "JUMP",
    "JUMP_IF_FALSE",
    "LOAD_HOST",
    "LOAD_ENV",
    "MAKE_MACRO",
    "MAKE_FUNCTION",
    "MOVE",
    "PARALLEL_GATHER",
    "PERFORM",
    "RAISE_EFFECT",
    "RACE_FIRST",
    "RESUME",
    "RETURN",
    "RUNTIME_EVAL",
    "STORE_LOCAL",
    "TAIL_CALL",
]


@dataclass(frozen=True, slots=True)
class OpcodeInfo:
    """Opcode 元数据。.

    Attributes:
        name: opcode 名称
        operand_count: 操作数数量，-1 表示可变数量
        has_dest: 是否有目标寄存器（第一个操作数）
        is_terminator: 是否是终结符（RETURN、JUMP、TAIL_CALL 等）
        is_branch: 是否是分支指令（JUMP_IF_FALSE、HANDLE 等）
    """

    name: str
    operand_count: int
    has_dest: bool
    is_terminator: bool
    is_branch: bool


OPCODE_TABLE: dict[str, OpcodeInfo] = {
    "APPEND_RESULT": OpcodeInfo(
        name="APPEND_RESULT",
        operand_count=1,
        has_dest=False,
        is_terminator=False,
        is_branch=False,
    ),
    "ALL_GATHER": OpcodeInfo(
        name="ALL_GATHER",
        operand_count=-1,  # dest + variadic sources
        has_dest=True,
        is_terminator=False,
        is_branch=False,
    ),
    "APPLY": OpcodeInfo(
        name="APPLY",
        operand_count=3,  # dest, func, args_tuple
        has_dest=True,
        is_terminator=False,
        is_branch=False,
    ),
    "BUILD_TUPLE": OpcodeInfo(
        name="BUILD_TUPLE",
        operand_count=-1,  # dest + variadic elements
        has_dest=True,
        is_terminator=False,
        is_branch=False,
    ),
    "CACHE_EVAL": OpcodeInfo(
        name="CACHE_EVAL",
        operand_count=2,  # dest, expr
        has_dest=True,
        is_terminator=False,
        is_branch=False,
    ),
    "CALL": OpcodeInfo(
        name="CALL",
        operand_count=-1,  # dest, func + variadic args
        has_dest=True,
        is_terminator=False,
        is_branch=False,
    ),
    "DEFEFFECT": OpcodeInfo(
        name="DEFEFFECT",
        operand_count=2,  # dest, name
        has_dest=True,
        is_terminator=False,
        is_branch=False,
    ),
    "DEFINE_MODULE": OpcodeInfo(
        name="DEFINE_MODULE",
        operand_count=2,  # name, exports_tuple
        has_dest=False,
        is_terminator=False,
        is_branch=False,
    ),
    "DEFINE_ONCE": OpcodeInfo(
        name="DEFINE_ONCE",
        operand_count=2,  # name, value_reg
        has_dest=False,
        is_terminator=False,
        is_branch=False,
    ),
    "ENTER_SCOPE": OpcodeInfo(
        name="ENTER_SCOPE",
        operand_count=0,
        has_dest=False,
        is_terminator=False,
        is_branch=False,
    ),
    "EXIT_SCOPE": OpcodeInfo(
        name="EXIT_SCOPE",
        operand_count=0,
        has_dest=False,
        is_terminator=False,
        is_branch=False,
    ),
    "FROM_IMPORT": OpcodeInfo(
        name="FROM_IMPORT",
        operand_count=2,  # module_path, imports_tuple
        has_dest=False,
        is_terminator=False,
        is_branch=False,
    ),
    "HANDLE": OpcodeInfo(
        name="HANDLE",
        operand_count=4,  # dest, effect_name, body_reg, handler_reg
        has_dest=True,
        is_terminator=False,
        is_branch=True,
    ),
    "JUMP": OpcodeInfo(
        name="JUMP",
        operand_count=1,  # target_label
        has_dest=False,
        is_terminator=True,
        is_branch=True,
    ),
    "JUMP_IF_FALSE": OpcodeInfo(
        name="JUMP_IF_FALSE",
        operand_count=2,  # condition_reg, target_label
        has_dest=False,
        is_terminator=False,
        is_branch=True,
    ),
    "LOAD_HOST": OpcodeInfo(
        name="LOAD_HOST",
        operand_count=2,  # dest, value
        has_dest=True,
        is_terminator=False,
        is_branch=False,
    ),
    "LOAD_ENV": OpcodeInfo(
        name="LOAD_ENV",
        operand_count=2,  # dest, symbol
        has_dest=True,
        is_terminator=False,
        is_branch=False,
    ),
    "MAKE_MACRO": OpcodeInfo(
        name="MAKE_MACRO",
        operand_count=2,  # dest, func_index
        has_dest=True,
        is_terminator=False,
        is_branch=False,
    ),
    "MAKE_FUNCTION": OpcodeInfo(
        name="MAKE_FUNCTION",
        operand_count=2,  # dest, func_index
        has_dest=True,
        is_terminator=False,
        is_branch=False,
    ),
    "MOVE": OpcodeInfo(
        name="MOVE",
        operand_count=2,  # dest, src
        has_dest=True,
        is_terminator=False,
        is_branch=False,
    ),
    "PARALLEL_GATHER": OpcodeInfo(
        name="PARALLEL_GATHER",
        operand_count=-1,  # dest + variadic sources
        has_dest=True,
        is_terminator=False,
        is_branch=False,
    ),
    "PERFORM": OpcodeInfo(
        name="PERFORM",
        operand_count=3,  # dest, effect_name, value_reg
        has_dest=True,
        is_terminator=False,
        is_branch=False,
    ),
    "RAISE_EFFECT": OpcodeInfo(
        name="RAISE_EFFECT",
        operand_count=2,  # effect_name, value_reg
        has_dest=False,
        is_terminator=True,
        is_branch=False,
    ),
    "RACE_FIRST": OpcodeInfo(
        name="RACE_FIRST",
        operand_count=-1,  # dest + variadic sources
        has_dest=True,
        is_terminator=False,
        is_branch=False,
    ),
    "RESUME": OpcodeInfo(
        name="RESUME",
        operand_count=2,  # dest, continuation_reg
        has_dest=True,
        is_terminator=False,
        is_branch=False,
    ),
    "RETURN": OpcodeInfo(
        name="RETURN",
        operand_count=1,  # value_reg
        has_dest=False,
        is_terminator=True,
        is_branch=False,
    ),
    "RUNTIME_EVAL": OpcodeInfo(
        name="RUNTIME_EVAL",
        operand_count=2,  # dest, expr_reg
        has_dest=True,
        is_terminator=False,
        is_branch=False,
    ),
    "STORE_LOCAL": OpcodeInfo(
        name="STORE_LOCAL",
        operand_count=2,  # name, value_reg
        has_dest=False,
        is_terminator=False,
        is_branch=False,
    ),
    "TAIL_CALL": OpcodeInfo(
        name="TAIL_CALL",
        operand_count=-1,  # func + variadic args
        has_dest=False,
        is_terminator=True,
        is_branch=False,
    ),
}
