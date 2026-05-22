# coding: utf-8
"""符号空间加载器。.

目标：
- 加载具名符号空间（模块）
- 管理模块缓存和依赖关系
- 提供统一的加载接口

当前：
- 实现基本的模块加载和缓存机制
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from qy.core.symbol_space import SymbolSpace

__all__ = [
    "ModuleLoader",
    "load_named_space",
]


class ModuleLoader:
    """模块加载器。.

    负责加载和缓存具名符号空间（模块）。
    """

    def __init__(self) -> None:
        self._cache: dict[str, SymbolSpace] = {}
        self._loading: set[str] = set()

    def load(self, name: str) -> SymbolSpace:
        """加载具名符号空间。.

        Args:
            name: 模块名称

        Returns:
            SymbolSpace: 加载的符号空间

        Raises:
            QyRuntimeError: 当模块不存在或存在循环依赖时
        """
        # 检查缓存
        if name in self._cache:
            return self._cache[name]

        # 检测循环依赖
        if name in self._loading:
            from qy.errors import QyRuntimeError

            raise QyRuntimeError(f"circular dependency detected: {name}")

        # 标记为正在加载
        self._loading.add(name)

        try:
            # 加载模块
            space = self._load_module(name)

            # 缓存
            self._cache[name] = space

            return space
        finally:
            # 移除加载标记
            self._loading.discard(name)

    def _load_module(self, name: str) -> SymbolSpace:
        """实际加载模块的逻辑。.

        这个方法应该被子类覆盖或通过依赖注入提供。
        """
        from qy.errors import QyRuntimeError

        raise QyRuntimeError(f"module loader not configured for {name!r}")

    def cache(self, name: str, space: SymbolSpace) -> None:
        """缓存模块。.

        Args:
            name: 模块名称
            space: 符号空间
        """
        self._cache[name] = space

    def has_cached(self, name: str) -> bool:
        """检查模块是否已缓存。.

        Args:
            name: 模块名称

        Returns:
            bool: 是否已缓存
        """
        return name in self._cache

    def clear_cache(self) -> None:
        """清空缓存。."""
        self._cache.clear()


# 全局加载器实例
_global_loader: ModuleLoader | None = None


def get_global_loader() -> ModuleLoader:
    """获取全局模块加载器。."""
    global _global_loader
    if _global_loader is None:
        _global_loader = ModuleLoader()
    return _global_loader


def set_global_loader(loader: ModuleLoader) -> None:
    """设置全局模块加载器。."""
    global _global_loader
    _global_loader = loader


def load_named_space(name: str) -> SymbolSpace:
    """加载具名符号空间。.

    这是一个便利函数，使用全局加载器加载模块。

    Args:
        name: 模块名称

    Returns:
        SymbolSpace: 加载的符号空间
    """
    return get_global_loader().load(name)
