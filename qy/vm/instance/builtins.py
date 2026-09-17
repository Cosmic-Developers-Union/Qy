# coding: utf-8
"""寄存器 VM 的内建算子实现表。.

`CALL_BUILTIN` 携带的是 `qy/core/operator_builtins.py` 里的内建下标；本模块把下标
映射到**语言实现自身**的算子实现体（`qy.std` / `qy.session` 里已有的函数），
从而跳过运行期的 symbol-space 查找与 `PureOperator` 对象分发。

单一语义来源：这里不重新实现任何算子语义，只做"下标 -> 既有实现"的取用。
宿主注入的同名覆盖不会进入内建路径——`lir.select_builtins` 在编译期已经核对过
会话 env 解析结果与标准实现是同一对象。

禁止：
- 不得在这里写第二份算子语义；
- 不得在这里做 symbol 解析以外的策略判断。
"""

from __future__ import annotations

from collections.abc import Callable
from functools import lru_cache

from qy.core.operator_builtins import BUILTIN_OPERATORS

__all__ = ["builtin_implementation", "call_builtin"]

BuiltinBody = Callable[..., object]


@lru_cache(maxsize=1)
def _implementations() -> tuple[BuiltinBody | None, ...]:
    """按内建下标取出标准实现体（惰性构建一次）。."""
    from qy.core.syntax import Symbol
    from qy.session.runtime_space import create_standard_runtime_space

    env = create_standard_runtime_space()
    bodies: list[BuiltinBody | None] = []
    for operator in BUILTIN_OPERATORS:
        try:
            value = env.resolve(Symbol(operator.name))
        except Exception:
            bodies.append(None)
            continue
        body = getattr(value, "func", None)
        bodies.append(body if callable(body) else None)
    return tuple(bodies)


def builtin_implementation(builtin_id: int) -> BuiltinBody | None:
    """返回内建下标对应的实现体；未知或缺失返回 None。."""
    bodies = _implementations()
    if 0 <= builtin_id < len(bodies):
        return bodies[builtin_id]
    return None


def call_builtin(builtin_id: int, args: tuple[object, ...]) -> object:
    """执行内建算子（语义实现取自 qy.std / qy.session）。."""
    from qy.errors import QyRuntimeError

    bodies = _implementations()
    if not 0 <= builtin_id < len(bodies):
        raise QyRuntimeError(f"unknown builtin operator index {builtin_id}")
    body = bodies[builtin_id]
    if body is None:
        raise QyRuntimeError(
            f"builtin operator {BUILTIN_OPERATORS[builtin_id].name!r} "
            "has no implementation in the standard profile"
        )
    return body(*args)
