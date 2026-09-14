# coding: utf-8
"""扩展注册表：按名注册 / 查询 / 装载扩展。."""

from __future__ import annotations

from collections.abc import Callable

from qy.ext.descriptor import ExtensionDescriptor
from qy.import_.module import StandardModule

__all__ = [
    "extension_descriptors",
    "extension_names",
    "get_extension",
    "load_extension",
    "register_extension",
]

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


def load_extension(name: str) -> StandardModule:
    """装载扩展提供的模块。.

    语言侧只能通过 ``from <module_name> import ...`` 使用扩展；装载结果就是
    普通 ``StandardModule``，语言内核不需要知道它是宿主实现。
    """
    factory = _FACTORIES[name]
    return factory()
