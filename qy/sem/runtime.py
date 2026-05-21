# coding: utf-8
# Copyright (C) 2025 Cosmic-Developers-Union (CDU), All rights reserved.

"""Runtime values for Qy semantic model.

This module defines runtime values that represent executable entities in the
semantic model: user-defined functions, effect definitions, and component
operators. These are semantic values shared across all backends, not
implementation-specific helpers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from qy.errors import QyArityError
from qy.reader import Symbol

if TYPE_CHECKING:
    from qy.environment import Environment

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
    mechanism depends on the backend (eval_runtime, register VM, etc.).
    """

    name: Symbol
    params: tuple[Symbol, ...]
    body: tuple[object, ...]
    closure: Environment

    async def __call__(self, *args: object) -> object:
        """Legacy execution path for eval_runtime.

        This will be removed after full migration to register VM. New code
        should not rely on this method.
        """
        from qy.eval_runtime import evaluate_tail_body_async
        from qy.vm.instance.values import TailCall

        if len(args) != len(self.params):
            raise QyArityError(
                f"{self.name.name} expects {len(self.params)} arguments, got {len(args)}",
                span=self.name.span,
                metadata={
                    "expected": len(self.params),
                    "actual": len(args),
                    "function": self.name.name,
                },
            )
        current_args = args
        while True:
            local_env = self.closure.child(dict(zip(self.params, current_args, strict=True)))
            result = await evaluate_tail_body_async(self.body, local_env, self)
            if not isinstance(result, TailCall) or result.function is not self:
                return result
            current_args = result.args


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

    async def __call__(self, *args: object) -> object:
        """Legacy execution path for eval_runtime.

        This will be removed after full migration to register VM. New code
        should not rely on this method.
        """
        from qy.core.syntax import list_to_chain
        from qy.eval_runtime import evaluate_async

        if len(args) == 0:
            raise QyArityError(
                "component operator expects at least 1 argument",
                metadata={"actual": 0},
            )

        if len(self.operators) == 1:
            # Single operator: direct call
            form = list_to_chain([self.operators[0], *args])
            return await evaluate_async(form, self.closure)

        # Multiple operators: first arg to first operator, rest to last
        first_arg = args[0]
        rest_args = args[1:]

        # Compose right-to-left: call last operator first
        if len(self.operators) == 2:
            # Two operators case
            op1, op2 = self.operators
            # Call op2 with remaining args
            form2 = list_to_chain([op2, *rest_args])
            result2 = await evaluate_async(form2, self.closure)
            # Call op1 with first arg and op2's result
            form1 = list_to_chain([op1, first_arg, result2])
            return await evaluate_async(form1, self.closure)
        else:
            # More than two operators: recursive composition
            # (component op1 op2 op3 ... opn) is equivalent to
            # (component op1 (component op2 op3 ... opn))
            rest_component = ComponentOperator(self.operators[1:], self.closure)
            result_rest = await rest_component(*rest_args)
            # Call first operator with first arg and composed result
            form1 = list_to_chain([self.operators[0], first_arg, result_rest])
            return await evaluate_async(form1, self.closure)
