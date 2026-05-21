# coding: utf-8
# QY_DELETE_AFTER_SEMANTIC_REPLACEMENT: target=qy/sem + qy/vm/instance runtime objects

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from qy.errors import QyArityError
from qy.reader import Symbol

if TYPE_CHECKING:
    from qy.environment import Environment

__all__ = ["ComponentOperator", "EffectDefinition", "HostObjectRef", "UserFunction"]


@dataclass(frozen=True, slots=True)
class EffectDefinition:
    name: Symbol
    resumable: bool = True
    doc: str = ""


@dataclass(frozen=True, slots=True, eq=False)
class HostObjectRef:
    value: object


@dataclass(frozen=True, slots=True)
class _TailCall:
    function: object
    args: tuple[object, ...]


@dataclass(frozen=True, slots=True)
class UserFunction:
    name: Symbol
    params: tuple[Symbol, ...]
    body: tuple[object, ...]
    closure: Environment

    async def __call__(self, *args: object) -> object:
        # legacy -- will be removed after UserFunction migration to register VM
        from qy.eval_runtime import evaluate_tail_body_async

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
            if not isinstance(result, _TailCall) or result.function is not self:
                return result
            current_args = result.args


@dataclass(frozen=True, slots=True)
class ComponentOperator:
    """组合多个算子的元算子。.

    当调用时，将第一个参数传给第一个算子，剩余参数传给最后一个算子，
    然后从右到左组合结果。
    """

    operators: tuple[object, ...]
    closure: Environment

    async def __call__(self, *args: object) -> object:
        from qy.core.syntax import list_to_chain
        from qy.eval_runtime import evaluate_async

        if len(args) == 0:
            raise QyArityError(
                "component operator expects at least 1 argument",
                metadata={"actual": 0},
            )

        if len(self.operators) == 1:
            # 只有一个算子，直接调用
            form = list_to_chain([self.operators[0], *args])
            return await evaluate_async(form, self.closure)

        # 多个算子：第一个参数给第一个算子，剩余参数给最后一个算子
        first_arg = args[0]
        rest_args = args[1:]

        # 从右到左组合：先调用最后一个算子
        if len(self.operators) == 2:
            # 两个算子的情况
            op1, op2 = self.operators
            # 用剩余参数调用 op2
            form2 = list_to_chain([op2, *rest_args])
            result2 = await evaluate_async(form2, self.closure)
            # 用第一个参数和 op2 的结果调用 op1
            form1 = list_to_chain([op1, first_arg, result2])
            return await evaluate_async(form1, self.closure)
        else:
            # 多于两个算子：递归组合
            # (component op1 op2 op3 ... opn) 等价于
            # (component op1 (component op2 op3 ... opn))
            rest_component = ComponentOperator(self.operators[1:], self.closure)
            result_rest = await rest_component(*rest_args)
            # 用第一个参数和剩余组合的结果调用第一个算子
            form1 = list_to_chain([self.operators[0], first_arg, result_rest])
            return await evaluate_async(form1, self.closure)
