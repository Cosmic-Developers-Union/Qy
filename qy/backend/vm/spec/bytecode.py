# coding: utf-8
"""Bytecode spec 目标模块。.

目标：
- 定义 bytecode program/function/instruction 的规格、编码约束和验证规则。
- 替代迁移期 `qy/bytecode.py` 中的规格部分。

当前：
- 从 qy/bytecode.py 迁移核心数据结构。
- 提供 VM target 层的 bytecode 规格，不包含 runtime value（如 BytecodeFunctionValue）。

禁止：
- 不得包含具体的执行逻辑。
- 不得依赖某个 Python VM instance。
- 不得混入 runtime value 或 closure 概念（那些属于 VM 实现层）。
"""

from __future__ import annotations

from dataclasses import dataclass

from qy.backend.vm.spec.opcode import Opcode

__all__ = [
    "FunctionSpec",
    "Instruction",
    "ProgramSpec",
    "Register",
]

Register = int


@dataclass(frozen=True, slots=True)
class Instruction:
    """单条 bytecode 指令。.

    Attributes:
        opcode: 操作码
        operands: 操作数元组，可以是 Register、Symbol、literal value、label 等
        span: 源码位置信息（可选）
    """

    opcode: Opcode
    operands: tuple[object, ...] = ()
    span: object | None = None


@dataclass(frozen=True, slots=True)
class FunctionSpec:
    """Bytecode 函数规格。.

    Attributes:
        name: 函数名（字符串形式）
        params: 参数名列表（字符串形式）
        register_count: 寄存器数量
        instructions: 指令序列
    """

    name: str
    params: tuple[str, ...]
    register_count: int
    instructions: tuple[Instruction, ...]


@dataclass(frozen=True, slots=True)
class ProgramSpec:
    """Bytecode 程序规格。.

    Attributes:
        functions: 函数列表
        main: 主函数索引（默认为 0）
    """

    functions: tuple[FunctionSpec, ...]
    main: int = 0
