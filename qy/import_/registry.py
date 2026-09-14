# coding: utf-8
"""模块注册表与按名加载。.

此模块负责"已知模块名 → ``StandardModule`` 工厂"的映射，以及
对包路径 (``foo/bar``) 与文件路径 (``./mod.qy``、``./mod.py``) 的
fallback 加载。

它本身不知道任何具体模块的内容；具体加载器在 ``qy.symbol_space`` 与
``qy.import_.operators`` 启动时调用 ``register_module_loader`` 注入。
"""

from __future__ import annotations

from collections.abc import Callable
from collections.abc import Iterable
from pathlib import Path
from typing import cast

from qy.frontend.reader import Symbol
from qy.import_.module import StandardModule

__all__ = [
    "FileModuleLoader",
    "ModuleLoader",
    "load_file_module",
    "load_module",
    "load_module_async",
    "module_names",
    "register_default_module_loader",
    "register_file_module_loader",
    "register_module",
    "register_module_loader",
    "standard_bindings",
    "standard_profile_bindings",
]

type ModuleLoader = Callable[[], StandardModule]
type FileModuleLoader = Callable[[Path], StandardModule]

_MODULE_LOADERS: dict[str, ModuleLoader] = {}
# File-suffix loaders are injected by extensions (e.g. qy.ext.python registers
# ``.py``). The kernel registry itself never knows host file formats.
_FILE_MODULE_LOADERS: dict[str, FileModuleLoader] = {}
_BUILTINS_INSTALLED = False


def register_file_module_loader(suffix: str, loader: FileModuleLoader) -> None:
    """注册某后缀文件的模块加载器（供扩展注入）。."""
    _FILE_MODULE_LOADERS[suffix] = loader


def _file_module_loader(suffix: str) -> FileModuleLoader | None:
    return _FILE_MODULE_LOADERS.get(suffix)


def register_module(module: StandardModule) -> None:
    """注册一个已构造好的模块；覆盖任何同名已有 loader。."""
    _MODULE_LOADERS[module.name] = lambda: module


def register_module_loader(name: str, loader: ModuleLoader) -> None:
    """注册模块 loader；覆盖任何同名已有 loader。."""
    _MODULE_LOADERS[name] = loader


def register_default_module_loader(name: str, loader: ModuleLoader) -> None:
    """以 ``setdefault`` 语义注册 loader：仅在尚未注册时生效。.

    内置 loader 应使用此函数，使得显式 ``register_module_loader`` 调用
    总能覆盖默认实现。
    """
    _MODULE_LOADERS.setdefault(name, loader)


def _ensure_builtins_installed() -> None:
    global _BUILTINS_INSTALLED
    if _BUILTINS_INSTALLED:
        return
    _BUILTINS_INSTALLED = True
    # qy.symbol_space 在 import-time 把内置 loader 注入注册表
    import qy.symbol_space  # noqa: F401


def module_names() -> tuple[str, ...]:
    _ensure_builtins_installed()
    return tuple(sorted(_MODULE_LOADERS))


def load_module(name: str) -> StandardModule:
    _ensure_builtins_installed()
    try:
        return _MODULE_LOADERS[name]()
    except KeyError as e:
        if _looks_like_package_path(name):
            return _load_package_module(name)
        if _looks_like_file_module(name):
            return _load_file_module(name)
        raise KeyError(f"unknown module {name!r}") from e


async def load_module_async(name: str) -> StandardModule:
    _ensure_builtins_installed()
    try:
        return _MODULE_LOADERS[name]()
    except KeyError as e:
        if _looks_like_package_path(name):
            return _load_package_module(name)
        if _looks_like_file_module(name):
            return await _load_file_module_async(name)
        raise KeyError(f"unknown module {name!r}") from e


def standard_profile_bindings(modules: Iterable[str]) -> dict[Symbol, object]:
    bindings: dict[Symbol, object] = {}
    for name in modules:
        bindings.update(load_module(name).exports)
    return bindings


def standard_bindings(modules: Iterable[str]) -> dict[Symbol, object]:
    return standard_profile_bindings(modules)


def _looks_like_file_module(name: str) -> bool:
    path = Path(name)
    return path.suffix in {".py", ".qy"} or "/" in name or "\\" in name or name.startswith(".")


def _looks_like_package_path(name: str) -> bool:
    from qy.project.package import is_package_path

    return is_package_path(name)


def _load_package_module(name: str) -> StandardModule:
    """从包缓存加载模块（无 env 上下文时的降级路径）。."""
    from qy.project.fetch import get_cached
    from qy.project.manifest import parse_manifest_file
    from qy.project.package import load_package
    from qy.project.package import split_package_module

    cwd = Path.cwd()
    manifest_path = cwd / "qy.toml"
    if not manifest_path.exists():
        raise KeyError(f"no qy.toml found, cannot resolve package module {name!r}")

    manifest = parse_manifest_file(manifest_path)
    known = {dep.path for dep in manifest.dependencies}
    pkg_path, submodule = split_package_module(name, known)

    for r in manifest.replaces:
        if r.path == pkg_path:
            local = (cwd / r.local_path).resolve()
            pkg = load_package(local)
            source = pkg.root_module_path if not submodule else pkg.resolve_submodule(submodule)
            if source is None or not source.exists():
                raise KeyError(f"module source not found: {name!r}")
            return _load_file_module(str(source))

    for dep in manifest.dependencies:
        if dep.path == pkg_path:
            cached = get_cached(pkg_path, dep.min_version)
            if cached is None:
                raise KeyError(
                    f"package {pkg_path!r}@{dep.min_version} not in cache, run `qy pkg add`"
                )
            pkg = load_package(cached.root)
            if submodule and not pkg.is_exported(submodule):
                raise KeyError(f"module {submodule!r} is not exported by package {pkg_path!r}")
            source = pkg.root_module_path if not submodule else pkg.resolve_submodule(submodule)
            if source is None or not source.exists():
                raise KeyError(f"module source not found: {name!r}")
            return _load_file_module(str(source))

    raise KeyError(f"package {pkg_path!r} not declared in dependencies")


def _load_file_module(name: str) -> StandardModule:
    path = Path(name).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    path = path.resolve()
    if not path.is_file():
        raise KeyError(f"module file {name!r} does not exist")
    extension_loader = _file_module_loader(path.suffix)
    if extension_loader is not None:
        return extension_loader(path)
    if path.suffix == ".qy":
        from qy.async_utils import run_coro

        return cast(StandardModule, run_coro(_load_qy_file_module_async(path)))
    raise KeyError(f"unsupported module file type {path.suffix!r}")


def load_file_module(name: str) -> StandardModule:
    """通过路径加载 ``.qy`` / ``.py`` 模块文件。."""
    return _load_file_module(name)


async def _load_file_module_async(name: str) -> StandardModule:
    path = Path(name).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    path = path.resolve()
    if not path.is_file():
        raise KeyError(f"module file {name!r} does not exist")
    extension_loader = _file_module_loader(path.suffix)
    if extension_loader is not None:
        return extension_loader(path)
    if path.suffix == ".qy":
        return await _load_qy_file_module_async(path)
    raise KeyError(f"unsupported module file type {path.suffix!r}")


async def _load_qy_file_module_async(path: Path) -> StandardModule:
    from qy.frontend.reader import read
    from qy.macro import MacroDefinition
    from qy.session.runtime_space import create_standard_runtime_space as standard_environment
    from qy.vm.instance.machine import evaluate_form_async as evaluate_async

    env = standard_environment()
    baseline_symbols = set(env.bindings())
    last_result: object = None

    for form in read(path.read_text(encoding="utf-8")):
        last_result = await evaluate_async(form, env)

    if isinstance(last_result, StandardModule):
        return last_result

    runtime_exports: dict[Symbol, object] = {}
    macro_exports: dict[Symbol, object] = {}
    for symbol, value in env.bindings().items():
        if symbol in baseline_symbols:
            continue
        if isinstance(value, MacroDefinition):
            macro_exports[symbol] = value
        else:
            runtime_exports[symbol] = value
    return StandardModule(_file_module_name(path), runtime_exports, macro_exports)


def _file_module_name(path: Path) -> str:
    return str(path)
