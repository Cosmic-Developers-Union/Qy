# coding: utf-8
"""Host reference：宿主对象进入 Qy runtime 的语义包装。.

``HostReference`` 是 Qy 语义模型的一部分（见 ``LANGUAGE.md`` §1.2）：宿主值
只能以 host reference 的身份进入语言，语言侧不得直接依赖宿主类型。
扩展（``qy.ext.*``）负责创建/解包 host reference；语言内核只把它当作一个
不透明 runtime value。
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["HostReference"]


@dataclass(frozen=True, slots=True, eq=False)
class HostReference:
    """Reference to a host value.

    Wraps a host object so it can travel through Qy runtime without being
    interpreted as a Qy value. Used by host extensions and embedding.
    """

    value: object
