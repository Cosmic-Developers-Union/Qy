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

from qy.core.operator_runtime import RuntimeArgumentMode
from qy.core.operator_runtime import RuntimeDispatchKind
from qy.core.operator_runtime import RuntimeOperatorSemantics
from qy.core.operator_runtime import operator_uses_raw_args
from qy.core.operator_runtime import runtime_operator_semantics
from qy.core.operator_runtime import validate_operator_arity
from qy.core.operator_signature import CORE_OPERATOR_SIGNATURES
from qy.core.operator_signature import STDLIB_OPERATOR_SIGNATURES
from qy.core.operator_signature import ArgumentPolicy
from qy.core.operator_signature import Arity
from qy.core.operator_signature import EffectSpec
from qy.core.operator_signature import OperatorSignature
from qy.core.operator_signature import format_arity_message
from qy.core.operator_signature import lookup_operator_signature
from qy.core.operators import ArgumentEvaluator
from qy.core.operators import ControlOperator
from qy.core.operators import EffectOperator
from qy.core.operators import EvaluationOperator
from qy.core.operators import MetaOperator
from qy.core.operators import PureOperator
from qy.core.operators import ScopeOperator
from qy.core.operators import SyntaxOperator
from qy.core.operators import value_uses_eager_arguments
from qy.core.symbol_space import BindingSlot
from qy.core.symbol_space import ChainFrame
from qy.core.symbol_space import SymbolSpace
from qy.core.symbol_space import SymbolSpaceChain
from qy.core.symbol_utils import ensure_symbol
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
    "CORE_OPERATOR_SIGNATURES",
    "STDLIB_OPERATOR_SIGNATURES",
    "ArgumentEvaluator",
    "ArgumentPolicy",
    "Arity",
    "BindingSlot",
    "Chain",
    "ChainFrame",
    "ControlOperator",
    "EffectOperator",
    "EffectSpec",
    "EvaluationOperator",
    "MetaOperator",
    "OperatorKind",
    "OperatorSignature",
    "PureOperator",
    "RuntimeArgumentMode",
    "RuntimeDispatchKind",
    "RuntimeOperatorSemantics",
    "ScopeOperator",
    "SymbolSpace",
    "SymbolSpaceChain",
    "SyntaxOperator",
    "TypeName",
    "car",
    "cdr",
    "chain_to_list",
    "chain_to_tuple",
    "cons",
    "ensure_symbol",
    "format_arity_message",
    "is_chain",
    "is_nil",
    "list_to_chain",
    "lookup_operator_signature",
    "nil",
    "operator_uses_raw_args",
    "runtime_operator_semantics",
    "tuple_to_chain",
    "validate_operator_arity",
    "value_uses_eager_arguments",
]

TypeName = Literal[
    "any",
    "bool",
    "chain",
    "char",
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
