# coding: utf-8
# Copyright (C) 2025 Cosmic-Developers-Union (CDU), All rights reserved.

"""Runtime values for Qy semantic model.

语言只产生两种可执行 runtime value：

- ``EffectDefinition``（``defeffect`` 声明）；
- ``BytecodeFunctionValue``（``lambda`` / ``defun`` / module-local defun 的正式
  运行期表示，定义在 `qy.vm.bytecode`，由寄存器 VM 执行）。

历史 ``UserFunction`` 与 ``qy.vm.instance.legacy_eval``（legacy 求值路径）已删除：
所有函数值都经完整管线编译成 bytecode。本模块不 import ``qy.vm``，避免 ``sem``
反向依赖具体 VM 实现。
"""

from __future__ import annotations

from dataclasses import dataclass

from qy.core.syntax import Symbol

__all__ = ["EffectDefinition"]


@dataclass(frozen=True, slots=True)
class EffectDefinition:
    """Effect definition in the semantic model.

    Represents a declared algebraic effect with its name and resumability.
    """

    name: Symbol
    resumable: bool = True
    doc: str = ""
