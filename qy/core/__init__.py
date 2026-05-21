# -*- coding: utf-8 -*-
# Copyright (C) 2025 Cosmic-Developers-Union (CDU), All rights reserved.

"""核心模型：语言核心抽象。.

目标：
- 保存语言核心模型，包括 symbol、immutable chain、binding slot
- 定义 operator/effect 声明的抽象接口
- 提供语言核心的不可变数据结构

当前：
- 承载 OperatorKind / TypeName 类型定义
- 大量实现仍散落在 reader.py、environment.py、operators.py、values.py

禁止：
- 不得混入 profile 便利算子（如 +、-）
- 不得包含具体的标准库实现
- 不得依赖特定的执行后端
"""

from __future__ import annotations

from typing import Literal

from qy.core.symbol_space import BindingSlot
from qy.core.symbol_space import ChainFrame
from qy.core.symbol_space import SymbolSpace
from qy.core.symbol_space import SymbolSpaceChain
from qy.core.syntax import Chain
from qy.core.syntax import car
from qy.core.syntax import cdr
from qy.core.syntax import chain_to_list
from qy.core.syntax import chain_to_tuple
from qy.core.syntax import cons
from qy.core.syntax import is_chain
from qy.core.syntax import is_nil
from qy.core.syntax import list_to_chain
from qy.core.syntax import nil
from qy.core.syntax import tuple_to_chain

__all__ = [
    "BindingSlot",
    "Chain",
    "ChainFrame",
    "OperatorKind",
    "SymbolSpace",
    "SymbolSpaceChain",
    "TypeName",
    "car",
    "cdr",
    "chain_to_list",
    "chain_to_tuple",
    "cons",
    "is_chain",
    "is_nil",
    "list_to_chain",
    "nil",
    "tuple_to_chain",
]

TypeName = Literal[
    "any",
    "bool",
    "chain",
    "dict",
    "effect",
    "function",
    "list",
    "nil",
    "none",
    "number",
    "operator",
    "set",
    "string",
    "symbol",
    "tuple",
    "T",
    "unknown",
]
OperatorKind = Literal["pure", "scope", "control", "effect", "meta"]
