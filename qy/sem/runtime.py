# coding: utf-8
# Copyright (C) 2025 Cosmic-Developers-Union (CDU), All rights reserved.

"""Runtime values for Qy semantic model.

This module defines runtime values that represent executable entities in the
semantic model: user-defined functions, effect definitions, and component
operators. These are semantic values shared across all backends, not
implementation-specific helpers.

执行这些值的 VM 路径在 ``qy.vm.instance.legacy_eval``；本模块不 import
``qy.vm``，避免 ``sem`` 反向依赖具体 VM 实现。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from qy.core.syntax import Symbol

if TYPE_CHECKING:
    from qy.session.runtime_space import RuntimeSpace as Environment

__all__ = ["ComponentOperator", "EffectDefinition", "UserFunction"]


@dataclass(frozen=True, slots=True)
class EffectDefinition:
    """Effect definition in the semantic model.

    Represents a declared algebraic effect with its name and resumability.
    """

    name: Symbol
    resumable: bool = True
    doc: str = ""


@dataclass(frozen=True, slots=True)
class UserFunction:
    """User-defined function in the semantic model.

    Represents a lambda or named function with its parameters, body, and
    closure environment. This is a semantic value; the actual execution
    mechanism depends on the backend (register VM, etc.).
    """

    name: Symbol
    params: tuple[Symbol, ...]
    body: tuple[object, ...]
    closure: Environment


@dataclass(frozen=True, slots=True)
class ComponentOperator:
    """Component operator in the semantic model.

    A meta-operator that composes multiple operators. When called, it passes
    the first argument to the first operator and remaining arguments to the
    last operator, then composes results from right to left.

    Example:
        (component op1 op2 op3) with args (a, b, c) evaluates as:
        (op1 a (op2 (op3 b c)))
    """

    operators: tuple[object, ...]
    closure: Environment
