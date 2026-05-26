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
from typing import cast

if TYPE_CHECKING:
    from qy.core.symbol_space import SymbolSpace
    from qy.import_.module import StandardModule
    from qy.project.package import Package
    from qy.session.runtime_space import RuntimeSpace as Environment

__all__ = [
    "ModuleLoader",
    "cache_source_module",
    "load_named_space",
    "lookup_source_module",
    "resolve_known_module",
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


_SOURCE_MODULE_CACHE_KEY = ("qy", "source_modules")


def cache_source_module(module: StandardModule, env: Environment) -> StandardModule:
    _source_module_cache(env)[module.name] = module
    return module


def lookup_source_module(name: str, env: Environment) -> StandardModule | None:
    return _source_module_cache(env).get(name)


def resolve_known_module(name: str, env: Environment) -> StandardModule:
    modules = _source_module_cache(env)
    if name in modules:
        return modules[name]

    from qy.project.package import is_package_path

    if is_package_path(name):
        return _resolve_package_module(name, env)

    from qy.import_.registry import load_module

    return load_module(name)


def _resolve_package_module(name: str, env: Environment) -> StandardModule:
    """从包系统解析模块。."""
    from qy.project.package import split_package_module

    pkg_cache = _package_registry(env)
    known_packages = set(pkg_cache.keys())

    if not known_packages:
        known_packages = _discover_packages_from_manifest(env)

    pkg_path, submodule = split_package_module(name, known_packages)

    if pkg_path in pkg_cache:
        pkg = pkg_cache[pkg_path]
    else:
        pkg = _load_package_for_module(pkg_path, env)
        if pkg is not None:
            pkg_cache[pkg_path] = pkg

    if pkg is None:
        raise KeyError(f"package {pkg_path!r} not found in dependency graph")

    if submodule and not pkg.is_exported(submodule):
        raise KeyError(f"module {submodule!r} is not exported by package {pkg_path!r}")

    source_path = pkg.root_module_path if not submodule else pkg.resolve_submodule(submodule)
    if source_path is None or not source_path.exists():
        raise KeyError(f"module source not found: {name!r}")

    from qy.import_.registry import load_file_module

    module = load_file_module(str(source_path))

    modules = _source_module_cache(env)
    modules[name] = module
    return module


def _discover_packages_from_manifest(env: Environment) -> set[str]:
    """从当前项目的 qy.toml 发现已声明的依赖包路径。."""
    from pathlib import Path

    from qy.project.manifest import parse_manifest_file

    cwd = Path.cwd()
    manifest_path = cwd / "qy.toml"
    if not manifest_path.exists():
        return set()

    manifest = parse_manifest_file(manifest_path)
    return {dep.path for dep in manifest.dependencies}


def _load_package_for_module(pkg_path: str, env: Environment) -> Package | None:
    """加载一个包实例（从缓存或本地 replace）。."""
    from pathlib import Path

    from qy.project.fetch import get_cached
    from qy.project.manifest import parse_manifest_file
    from qy.project.package import load_package

    cwd = Path.cwd()
    manifest_path = cwd / "qy.toml"
    if not manifest_path.exists():
        return None

    manifest = parse_manifest_file(manifest_path)

    for r in manifest.replaces:
        if r.path == pkg_path:
            local = (cwd / r.local_path).resolve()
            if local.exists():
                return load_package(local)

    for dep in manifest.dependencies:
        if dep.path == pkg_path:
            cached = get_cached(pkg_path, dep.min_version)
            if cached is not None:
                return load_package(cached.root)
            break

    return None


_PACKAGE_REGISTRY_KEY = ("qy", "package_registry")


def _package_registry(env: Environment) -> dict[str, Package]:
    try:
        value = env.cache_lookup(_PACKAGE_REGISTRY_KEY)
    except KeyError:
        value = env.cache_define(_PACKAGE_REGISTRY_KEY, {})
    return cast("dict[str, Package]", value)


def _source_module_cache(env: Environment) -> dict[str, StandardModule]:
    try:
        value = env.cache_lookup(_SOURCE_MODULE_CACHE_KEY)
    except KeyError:
        value = env.cache_define(_SOURCE_MODULE_CACHE_KEY, {})
    return cast("dict[str, StandardModule]", value)
