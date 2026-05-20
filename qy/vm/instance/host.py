# coding: utf-8
"""VM 宿主适配器。.

目标：管理 host reference、host operator、host capability 的适配。
当前：目标接口定义。
禁止：不得定义语言语义。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class HostCallable(Protocol):
    """宿主可调用对象的协议。."""

    async def __call__(self, *args: object) -> object: ...


@dataclass(frozen=True, slots=True)
class HostAdapter:
    """宿主适配器配置。."""

    name: str
    callable: HostCallable
    eager: bool = True
