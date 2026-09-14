# coding: utf-8
"""扩展声明模型。.

扩展是 Qy 与宿主环境之间唯一的官方边界。声明是纯数据，不引用任何宿主
实现；实现由 :mod:`qy.ext.registry` 按名注册。
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field

from qy.core.operator_signature import OperatorSignature

__all__ = [
    "ExtensionBinding",
    "ExtensionCapability",
    "ExtensionDescriptor",
]


@dataclass(frozen=True, slots=True)
class ExtensionCapability:
    """一项宿主 capability（例如 python-exec / filesystem / process）。.

    扩展声明自己 *需要* 的 capability；实例/profile 可以据此决定是否装载，
    工具链也可以据此给出安全提示。
    """

    name: str
    doc: str = ""


@dataclass(frozen=True, slots=True)
class ExtensionBinding:
    """扩展对外暴露的一个 binding。.

    ``kind`` 使用与 ``OperatorKind`` 相同的词汇（pure/scope/control/effect/
    meta），也可以是 ``"value"`` 表示常量 binding。工具链必须只依赖这里的
    声明理解扩展算子，不得读取宿主实现细节。
    """

    name: str
    kind: str = "effect"
    doc: str = ""
    signature: OperatorSignature | None = None
    capabilities: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ExtensionDescriptor:
    """一个扩展的完整声明。."""

    name: str
    #: 语言侧可 ``from <module_name> import ...`` 的模块名；loader-only 扩展为 None。
    module_name: str | None
    version: str = "0.1"
    description: str = ""
    capabilities: tuple[ExtensionCapability, ...] = ()
    bindings: tuple[ExtensionBinding, ...] = ()
    metadata: tuple[tuple[str, str], ...] = field(default_factory=tuple)
