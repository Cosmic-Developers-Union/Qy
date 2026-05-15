# coding: utf-8

from __future__ import annotations

import importlib.util
import types
from collections.abc import Callable
from collections.abc import Iterable
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from qy.reader import Symbol
from qy.stdlib.module import StandardModule

__all__ = [
    "PRELUDE_MODULES",
    "StandardModule",
    "load_module",
    "load_module_async",
    "module_names",
    "register_module",
    "register_module_loader",
    "standard_bindings",
]

PRELUDE_MODULES = ("qy.core", "qy.io")
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
        if _looks_like_file_module(name):
            return _load_file_module(name)
        raise KeyError(f"unknown module {name!r}") from e


async def load_module_async(name: str) -> StandardModule:
    _install_builtin_loaders()
    try:
        return _MODULE_LOADERS[name]()
    except KeyError as e:
        if _looks_like_file_module(name):
            return await _load_file_module_async(name)
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
    _MODULE_LOADERS.setdefault("qy.py", _load_py_module)
    _MODULE_LOADERS.setdefault("qy.legacy", _load_legacy_module)


def _load_core_module() -> StandardModule:
    from qy.stdlib.core import module

    return module()


def _load_io_module() -> StandardModule:
    from qy.stdlib.io import module

    return module()


def _load_string_module() -> StandardModule:
    from qy.stdlib.strings import module

    return module()


def _load_py_module() -> StandardModule:
    from qy.stdlib.python import operators as python_operators

    return StandardModule("qy.py", python_operators())


def _load_legacy_module() -> StandardModule:
    from qy.stdlib.control import legacy_operators as control_legacy
    from qy.stdlib.effects import legacy_operators as effects_legacy

    return StandardModule("qy.legacy", {**control_legacy(), **effects_legacy()})


def _looks_like_file_module(name: str) -> bool:
    path = Path(name)
    return path.suffix in {".py", ".qy"} or "/" in name or "\\" in name or name.startswith(".")


def _load_file_module(name: str) -> StandardModule:
    path = Path(name).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    path = path.resolve()
    if not path.is_file():
        raise KeyError(f"module file {name!r} does not exist")
    if path.suffix == ".py":
        return _load_python_file_module(path)
    if path.suffix == ".qy":
        from qy.async_runtime import run_async

        return cast(StandardModule, run_async(_load_qy_file_module_async(path)))
    raise KeyError(f"unsupported module file type {path.suffix!r}")


async def _load_file_module_async(name: str) -> StandardModule:
    path = Path(name).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    path = path.resolve()
    if not path.is_file():
        raise KeyError(f"module file {name!r} does not exist")
    if path.suffix == ".py":
        return _load_python_file_module(path)
    if path.suffix == ".qy":
        return await _load_qy_file_module_async(path)
    raise KeyError(f"unsupported module file type {path.suffix!r}")


def _load_python_file_module(path: Path) -> StandardModule:
    module_name = f"_qy_external_{abs(hash(path))}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise KeyError(f"cannot load Python module file {str(path)!r}")

    python_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(python_module)

    if hasattr(python_module, "module"):
        module_factory = python_module.module
        if not callable(module_factory):
            raise ValueError(f"{str(path)!r} module attribute must be callable")
        return _coerce_standard_module(module_factory(), path)

    if hasattr(python_module, "exports"):
        return _module_from_exports(python_module.exports, path)

    return _module_from_public_callables(python_module, path)


async def _load_qy_file_module_async(path: Path) -> StandardModule:
    from qy.environment import standard_environment
    from qy.eval_runtime import evaluate_async
    from qy.macro import MacroDefinition
    from qy.reader import read

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


def _coerce_standard_module(value: object, path: Path) -> StandardModule:
    if isinstance(value, StandardModule):
        return value
    return _module_from_exports(value, path)


def _module_from_exports(value: object, path: Path) -> StandardModule:
    if not isinstance(value, Mapping):
        raise ValueError(f"{str(path)!r} exports must be a mapping")
    exports: dict[Symbol, object] = {}
    for name, exported_value in value.items():
        symbol = name if isinstance(name, Symbol) else Symbol(str(name))
        exports[symbol] = _coerce_python_export(symbol.name, exported_value)
    return StandardModule(_file_module_name(path), exports)


def _module_from_public_callables(module: types.ModuleType, path: Path) -> StandardModule:
    exports: dict[Symbol, object] = {}
    for name, value in vars(module).items():
        if name.startswith("_") or not callable(value) or isinstance(value, type):
            continue
        export_names = {name}
        if "_" in name:
            export_names.add(name.replace("_", "-"))
        for export_name in export_names:
            exports[Symbol(export_name)] = _coerce_python_export(export_name, value)
    return StandardModule(_file_module_name(path), exports)


def _coerce_python_export(name: str, value: object) -> object:
    from qy.macro import MacroDefinition
    from qy.operators import ControlOperator
    from qy.operators import EffectOperator
    from qy.operators import MetaOperator
    from qy.operators import PureOperator
    from qy.operators import ScopeOperator
    from qy.runtime_values import UserFunction

    if isinstance(
        value,
        PureOperator
        | ScopeOperator
        | ControlOperator
        | EffectOperator
        | MetaOperator
        | MacroDefinition
        | UserFunction,
    ):
        return value
    if callable(value):
        return PureOperator(name, value)
    return value


def _file_module_name(path: Path) -> str:
    return str(path)
