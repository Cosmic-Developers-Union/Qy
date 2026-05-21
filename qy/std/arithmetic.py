# coding: utf-8

from __future__ import annotations

import operator

from qy.core.operators import PureOperator
from qy.errors import QyTypeError
from qy.reader import Symbol


def _ensure_number(value: object) -> int | float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise QyTypeError(f"expected number, got {value!r}", metadata={"value": value})
    return value


def _py_eq(left: object, right: object) -> object:
    from qy.values import QY_NIL
    from qy.values import QY_T

    return QY_T if left == right else QY_NIL


def _num_eq(left: object, right: object) -> object:
    from qy.values import QY_NIL
    from qy.values import QY_T

    if isinstance(left, bool) or isinstance(right, bool):
        return QY_T if left is right else QY_NIL
    if isinstance(left, int | float) and isinstance(right, int | float):
        return QY_T if left == right else QY_NIL
    return QY_T if left is right else QY_NIL


def _add(*args: object) -> int | float:
    return sum(_ensure_number(arg) for arg in args)


def _sub(first: object, *rest: object) -> int | float:
    first_number = _ensure_number(first)
    if not rest:
        return -first_number
    return first_number - sum(_ensure_number(arg) for arg in rest)


def _mul(*args: object) -> int | float:
    result: int | float = 1
    for arg in args:
        result = operator.mul(result, _ensure_number(arg))
    return result


def _div(first: object, *rest: object) -> int | float:
    result = _ensure_number(first)
    if not rest:
        return 1 / result
    for arg in rest:
        result = operator.truediv(result, _ensure_number(arg))
    return result


def operators() -> dict[Symbol, object]:
    return {
        Symbol("="): PureOperator("=", _num_eq, "数值相等比较。"),
        Symbol("=="): PureOperator("==", _py_eq, "按 Python == 语义比较两个值。（兼容层）"),
        Symbol("+"): PureOperator("+", _add, "数字求和。"),
        Symbol("-"): PureOperator("-", _sub, "数字相减；单参数时取负。"),
        Symbol("*"): PureOperator("*", _mul, "数字相乘。"),
        Symbol("/"): PureOperator("/", _div, "数字相除；单参数时取倒数。"),
    }
