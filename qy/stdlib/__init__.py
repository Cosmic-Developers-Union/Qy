# coding: utf-8

from __future__ import annotations

from collections.abc import Callable
from collections.abc import Iterable

from qy.reader import Symbol
from qy.stdlib.module import StandardModule

__all__ = [
    "PRELUDE_MODULES",
    "StandardModule",
    "load_module",
    "module_names",
    "register_module",
    "register_module_loader",
    "standard_bindings",
]

PRELUDE_MODULES = ("qy.core", "qy.io", "qy.str")
type ModuleLoader = Callable[[], StandardModule]

_MODULE_LOADERS: dict[str, ModuleLoader] = {}


def module_names() -> tuple[str, ...]:
    _install_builtin_loaders()
    return tuple(sorted(_MODULE_LOADERS))


def register_module(module: StandardModule) -> None:
    _MODULE_LOADERS[module.name] = lambda: module


def register_module_loader(name: str, loader: ModuleLoader) -> None:
    _MODULE_LOADERS[name] = loader


def load_module(name: str) -> StandardModule:
    _install_builtin_loaders()
    try:
        return _MODULE_LOADERS[name]()
    except KeyError as e:
        raise KeyError(f"unknown module {name!r}") from e


def standard_bindings(modules: Iterable[str] = PRELUDE_MODULES) -> dict[Symbol, object]:
    bindings: dict[Symbol, object] = {}
    for name in modules:
        bindings.update(load_module(name).exports)
    return bindings


def _install_builtin_loaders() -> None:
    _MODULE_LOADERS.setdefault("qy.core", _load_core_module)
    _MODULE_LOADERS.setdefault("qy.io", _load_io_module)
    _MODULE_LOADERS.setdefault("qy.str", _load_string_module)


def _load_core_module() -> StandardModule:
    from qy.stdlib.core import module

    return module()


def _load_io_module() -> StandardModule:
    from qy.stdlib.io import module

    return module()


def _load_string_module() -> StandardModule:
    from qy.stdlib.strings import module

    return module()
