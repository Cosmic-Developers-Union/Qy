# coding: utf-8
"""符号空间折叠和展开解析器。.

目标：
- 解析 fold 和 unfold 操作的语义
- 处理命名冲突检测
- 提供符号选择和别名映射

当前：
- 实现 fold/unfold 的核心解析逻辑
"""

from __future__ import annotations

from collections.abc import Iterable
from collections.abc import Mapping
from dataclasses import dataclass

from qy.errors import QyRuntimeError
from qy.reader import Symbol

__all__ = [
    "FoldSpec",
    "UnfoldSpec",
    "resolve_fold",
    "resolve_unfold",
]


@dataclass(frozen=True, slots=True)
class FoldSpec:
    """折叠操作规范。.

    描述如何将多个符号空间合成为一个符号空间。
    - source_bindings: 源符号空间的绑定
    - selected_names: 要折叠的符号名称列表
    - alias_map: 符号别名映射 (原名 -> 新名)
    """

    source_bindings: Mapping[Symbol, object]
    selected_names: tuple[Symbol, ...]
    alias_map: Mapping[Symbol, Symbol]

    def apply_aliases(self) -> dict[Symbol, object]:
        """应用别名映射，返回最终的绑定字典。."""
        result: dict[Symbol, object] = {}
        for name in self.selected_names:
            if name not in self.source_bindings:
                raise QyRuntimeError(f"source has no export {name.name!r}")
            target_name = self.alias_map.get(name, name)
            result[target_name] = self.source_bindings[name]
        return result


@dataclass(frozen=True, slots=True)
class UnfoldSpec:
    """展开操作规范。.

    描述如何在一个符号空间内部展开另一个符号空间。
    - source_bindings: 源符号空间的绑定
    - selected_names: 要展开的符号名称列表（None 表示全部）
    - prefix: 展开后的符号前缀（用于避免冲突）
    """

    source_bindings: Mapping[Symbol, object]
    selected_names: tuple[Symbol, ...] | None
    prefix: str

    def apply_prefix(self) -> dict[Symbol, object]:
        """应用前缀，返回展开后的绑定字典。."""
        result: dict[Symbol, object] = {}
        names = (
            self.selected_names if self.selected_names is not None else self.source_bindings.keys()
        )

        for name in names:
            if name not in self.source_bindings:
                raise QyRuntimeError(f"source has no export {name.name!r}")

            if self.prefix:
                target_name = Symbol(f"{self.prefix}{name.name}", name.span)
            else:
                target_name = name

            result[target_name] = self.source_bindings[name]

        return result


def resolve_fold(
    source: Mapping[Symbol, object],
    names: Iterable[Symbol],
    aliases: Mapping[Symbol, Symbol] | None = None,
) -> FoldSpec:
    """解析折叠操作。.

    Args:
        source: 源符号空间的绑定
        names: 要折叠的符号名称
        aliases: 可选的别名映射

    Returns:
        FoldSpec: 折叠操作规范

    Raises:
        QyRuntimeError: 当源中缺少指定的符号时
    """
    selected = tuple(names)
    alias_map = dict(aliases or {})

    # 验证所有符号都存在
    for name in selected:
        if name not in source:
            raise QyRuntimeError(f"source has no export {name.name!r}")

    return FoldSpec(
        source_bindings=source,
        selected_names=selected,
        alias_map=alias_map,
    )


def resolve_unfold(
    source: Mapping[Symbol, object],
    names: Iterable[Symbol] | None = None,
    prefix: str = "",
) -> UnfoldSpec:
    """解析展开操作。.

    Args:
        source: 源符号空间的绑定
        names: 要展开的符号名称（None 表示全部）
        prefix: 展开后的符号前缀

    Returns:
        UnfoldSpec: 展开操作规范

    Raises:
        QyRuntimeError: 当源中缺少指定的符号时
    """
    selected = tuple(names) if names is not None else None

    # 验证所有符号都存在
    if selected is not None:
        for name in selected:
            if name not in source:
                raise QyRuntimeError(f"source has no export {name.name!r}")

    return UnfoldSpec(
        source_bindings=source,
        selected_names=selected,
        prefix=prefix,
    )


def detect_conflicts(
    target: Mapping[Symbol, object],
    incoming: Mapping[Symbol, object],
) -> list[Symbol]:
    """检测命名冲突。.

    Args:
        target: 目标符号空间的绑定
        incoming: 即将导入的绑定

    Returns:
        list[Symbol]: 冲突的符号列表
    """
    conflicts: list[Symbol] = []
    for name in incoming:
        if name in target:
            conflicts.append(name)
    return conflicts
