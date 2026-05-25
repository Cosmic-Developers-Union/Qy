# coding: utf-8

from __future__ import annotations

import importlib.util
import types
from collections.abc import Callable
from collections.abc import Iterable
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from qy.frontend.reader import Symbol
from qy.std.module import StandardModule

__all__ = [
    "LANGUAGE_CORE_MODULES",
    "OPTIONAL_STDLIB_MODULES",
    "PRELUDE_MODULES",
    "STANDARD_PROFILE_MODULES",
    "StandardModule",
    "load_module",
    "load_module_async",
    "module_names",
    "register_module",
    "register_module_loader",
    "standard_bindings",
    "standard_profile_bindings",
]

LANGUAGE_CORE_MODULES = ("qy.core",)
STANDARD_PROFILE_MODULES = ("qy.core", "qy.io")
OPTIONAL_STDLIB_MODULES = (
    "qy.num",
    "qy.str",
    "qy.char",
    "qy.py",
    "qy.testhost",
    "qy.legacy",
    "qy.int8",
    "qy.int16",
    "qy.int32",
    "qy.int64",
    "qy.uint8",
    "qy.uint16",
    "qy.uint32",
    "qy.uint64",
    "qy.float16",
    "qy.float32",
    "qy.float64",
    "qy.float128",
)
PRELUDE_MODULES = STANDARD_PROFILE_MODULES
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
        if _looks_like_package_path(name):
            return _load_package_module(name)
        if _looks_like_file_module(name):
            return _load_file_module(name)
        raise KeyError(f"unknown module {name!r}") from e


async def load_module_async(name: str) -> StandardModule:
    _install_builtin_loaders()
    try:
        return _MODULE_LOADERS[name]()
    except KeyError as e:
        if _looks_like_package_path(name):
            return _load_package_module(name)
        if _looks_like_file_module(name):
            return await _load_file_module_async(name)
        raise KeyError(f"unknown module {name!r}") from e


def standard_profile_bindings(
    modules: Iterable[str] = STANDARD_PROFILE_MODULES,
) -> dict[Symbol, object]:
    bindings: dict[Symbol, object] = {}
    for name in modules:
        bindings.update(load_module(name).exports)
    return bindings


def standard_bindings(modules: Iterable[str] = STANDARD_PROFILE_MODULES) -> dict[Symbol, object]:
    return standard_profile_bindings(modules)


def _install_builtin_loaders() -> None:
    _MODULE_LOADERS.setdefault("qy.core", _load_core_module)
    _MODULE_LOADERS.setdefault("qy.io", _load_io_module)
    _MODULE_LOADERS.setdefault("qy.num", _load_num_module)
    _MODULE_LOADERS.setdefault("qy.str", _load_string_module)
    _MODULE_LOADERS.setdefault("qy.char", _load_char_module)
    _MODULE_LOADERS.setdefault("qy.py", _load_py_module)
    _MODULE_LOADERS.setdefault("qy.testhost", _load_testhost_module)
    _MODULE_LOADERS.setdefault("qy.legacy", _load_legacy_module)
    # Hardware numeric spaces
    _MODULE_LOADERS.setdefault("qy.int8", _load_int8_module)
    _MODULE_LOADERS.setdefault("qy.int16", _load_int16_module)
    _MODULE_LOADERS.setdefault("qy.int32", _load_int32_module)
    _MODULE_LOADERS.setdefault("qy.int64", _load_int64_module)
    _MODULE_LOADERS.setdefault("qy.uint8", _load_uint8_module)
    _MODULE_LOADERS.setdefault("qy.uint16", _load_uint16_module)
    _MODULE_LOADERS.setdefault("qy.uint32", _load_uint32_module)
    _MODULE_LOADERS.setdefault("qy.uint64", _load_uint64_module)
    _MODULE_LOADERS.setdefault("qy.float16", _load_float16_module)
    _MODULE_LOADERS.setdefault("qy.float32", _load_float32_module)
    _MODULE_LOADERS.setdefault("qy.float64", _load_float64_module)
    _MODULE_LOADERS.setdefault("qy.float128", _load_float128_module)


def _load_core_module() -> StandardModule:
    from qy.std.core import module

    return module()


def _load_io_module() -> StandardModule:
    from qy.std.io import module

    return module()


def _load_num_module() -> StandardModule:
    from qy.std.arithmetic import operators as arithmetic_operators

    return StandardModule("qy.num", arithmetic_operators())


def _load_string_module() -> StandardModule:
    from qy.std.strings import module

    return module()


def _load_char_module() -> StandardModule:
    from qy.std.chars import module

    return module()


def _load_py_module() -> StandardModule:
    from qy.std.python import operators as python_operators

    return StandardModule("qy.py", python_operators())


def _load_legacy_module() -> StandardModule:
    from qy.std.control import legacy_operators as control_legacy
    from qy.std.effects import legacy_operators as effects_legacy

    return StandardModule("qy.legacy", {**control_legacy(), **effects_legacy()})


def _load_testhost_module() -> StandardModule:
    from qy.std.testhost import module

    return module()


# Hardware numeric space loaders
def _load_int8_module() -> StandardModule:
    from qy.std.numeric_spaces import make_int8_space

    return make_int8_space()


def _load_int16_module() -> StandardModule:
    from qy.std.numeric_spaces import make_int16_space

    return make_int16_space()


def _load_int32_module() -> StandardModule:
    from qy.std.numeric_spaces import make_int32_space

    return make_int32_space()


def _load_int64_module() -> StandardModule:
    from qy.std.numeric_spaces import make_int64_space

    return make_int64_space()


def _load_uint8_module() -> StandardModule:
    from qy.std.numeric_spaces import make_uint8_space

    return make_uint8_space()


def _load_uint16_module() -> StandardModule:
    from qy.std.numeric_spaces import make_uint16_space

    return make_uint16_space()


def _load_uint32_module() -> StandardModule:
    from qy.std.numeric_spaces import make_uint32_space

    return make_uint32_space()


def _load_uint64_module() -> StandardModule:
    from qy.std.numeric_spaces import make_uint64_space

    return make_uint64_space()


def _load_float16_module() -> StandardModule:
    from qy.std.numeric_spaces import make_float16_space

    return make_float16_space()


def _load_float32_module() -> StandardModule:
    from qy.std.numeric_spaces import make_float32_space

    return make_float32_space()


def _load_float64_module() -> StandardModule:
    from qy.std.numeric_spaces import make_float64_space

    return make_float64_space()


def _load_float128_module() -> StandardModule:
    from qy.std.numeric_spaces import make_float128_space

    return make_float128_space()


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

    # check replace directives
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
    if path.suffix == ".py":
        return _load_python_file_module(path)
    if path.suffix == ".qy":
        from qy.async_utils import run_coro

        return cast(StandardModule, run_coro(_load_qy_file_module_async(path)))
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
    from qy.core.operators import ControlOperator
    from qy.core.operators import EffectOperator
    from qy.core.operators import MetaOperator
    from qy.core.operators import PureOperator
    from qy.core.operators import ScopeOperator
    from qy.macro import MacroDefinition
    from qy.sem.runtime import UserFunction

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
