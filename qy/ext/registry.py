# coding: utf-8
"""扩展注册表：按名注册 / 查询 / 装载扩展。."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from qy.errors import QyCapabilityError
from qy.ext.descriptor import ExtensionDescriptor
from qy.import_.module import StandardModule

__all__ = [
    "ExtensionPolicy",
    "extension_descriptors",
    "extension_names",
    "extension_requires",
    "get_extension",
    "load_extension",
    "register_extension",
]


@dataclass(frozen=True, slots=True)
class ExtensionPolicy:
    """实例/工具对扩展与宿主 capability 的选择。.

    ``None`` 表示不限制；空集合表示全部拒绝。默认（未提供 policy）等价于
    不限制，保持显式 ``from`` 的既有行为。
    """

    enabled_extensions: frozenset[str] | None = None
    allowed_capabilities: frozenset[str] | None = None

    def allows_extension(self, name: str) -> bool:
        if self.enabled_extensions is None:
            return True
        return name in self.enabled_extensions

    def allows_capability(self, name: str) -> bool:
        if self.allowed_capabilities is None:
            return True
        return name in self.allowed_capabilities


def extension_requires(name: str) -> tuple[str, ...]:
    """返回扩展声明的 capability 名（含 binding 级 capability，去重排序）。."""
    descriptor = get_extension(name)
    required: set[str] = {capability.name for capability in descriptor.capabilities}
    for binding in descriptor.bindings:
        required.update(binding.capabilities)
    return tuple(sorted(required))


_EXTENSIONS: dict[str, ExtensionDescriptor] = {}
_FACTORIES: dict[str, Callable[[], StandardModule]] = {}


def register_extension(
    descriptor: ExtensionDescriptor,
    factory: Callable[[], StandardModule],
) -> None:
    """注册一个扩展声明及其模块工厂。同名重复注册覆盖旧实现。."""
    _EXTENSIONS[descriptor.name] = descriptor
    _FACTORIES[descriptor.name] = factory


def get_extension(name: str) -> ExtensionDescriptor:
    """返回扩展声明；未注册时抛 ``KeyError``。."""
    return _EXTENSIONS[name]


def extension_names() -> tuple[str, ...]:
    """返回全部已注册扩展名（排序）。."""
    return tuple(sorted(_EXTENSIONS))


def extension_descriptors() -> tuple[ExtensionDescriptor, ...]:
    """返回全部扩展声明（按名字排序）。."""
    return tuple(_EXTENSIONS[name] for name in extension_names())


def load_extension(
    name: str,
    *,
    policy: ExtensionPolicy | None = None,
) -> StandardModule:
    """装载扩展提供的模块。.

    语言侧只能通过 ``from <module_name> import ...`` 使用扩展；装载结果就是
    普通 ``StandardModule``，语言内核不需要知道它是宿主实现。

    提供 ``policy`` 时按扩展/capability 声明做准入检查；违反时抛
    ``QyCapabilityError``。
    """
    if policy is not None and not policy.allows_extension(name):
        raise QyCapabilityError(
            f"extension {name!r} is not enabled by policy",
            metadata={"extension": name},
        )
    if policy is not None:
        for capability in extension_requires(name):
            if not policy.allows_capability(capability):
                raise QyCapabilityError(
                    f"extension {name!r} requires capability {capability!r} "
                    "which is not allowed by policy",
                    metadata={"extension": name, "capability": capability},
                )
    factory = _FACTORIES[name]
    return factory()
