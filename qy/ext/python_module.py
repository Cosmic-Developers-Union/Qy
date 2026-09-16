# coding: utf-8
"""``qy.ext.python-modules``：宿主 ``.py`` 文件模块扩展。.

把「直接加载宿主 Python 文件为 Qy 模块」这一宿主能力从内核 import
注册表移到扩展边界：

- 内核只保留通用的 file-suffix loader hook；
- 本扩展注册 ``.py`` 后缀 loader，并声明 ``host-python-modules`` capability；
- Python 导出被强制转换为 Qy binding：``module()`` 工厂、``exports`` 映射或
  公开 callable，且 callable 一律包装为 host reference 或在调用时转换。
"""

from __future__ import annotations

import importlib.util
import types
from pathlib import Path

from qy.core.operators import ControlOperator
from qy.core.operators import EffectOperator
from qy.core.operators import MetaOperator
from qy.core.operators import PureOperator
from qy.core.operators import ScopeOperator
from qy.core.syntax import Symbol
from qy.errors import QyPythonError
from qy.ext.descriptor import ExtensionBinding
from qy.ext.descriptor import ExtensionCapability
from qy.ext.descriptor import ExtensionDescriptor
from qy.ext.registry import register_extension
from qy.import_.module import StandardModule
from qy.import_.registry import register_file_module_loader

__all__ = ["DESCRIPTOR", "load_python_file_module", "module"]


def _file_module_name(path: Path) -> str:
    return path.stem


def _module_from_exports(value: object, path: Path) -> StandardModule:
    from collections.abc import Mapping

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


def _coerce_standard_module(value: object, path: Path) -> StandardModule:
    if isinstance(value, StandardModule):
        return value
    return _module_from_exports(value, path)


def _coerce_python_export(name: str, value: object) -> object:
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


def load_python_file_module(path: Path) -> StandardModule:
    """加载宿主 Python 文件为 Qy 模块（扩展内部实现）。."""
    module_name = f"_qy_external_{abs(hash(path))}"
    try:
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            raise KeyError(f"cannot load Python module file {str(path)!r}")
        python_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(python_module)
    except OSError as e:
        raise QyPythonError(f"cannot read Python module file {str(path)!r}: {e}") from e

    if hasattr(python_module, "module"):
        module_factory = python_module.module
        if not callable(module_factory):
            raise ValueError(f"{str(path)!r} module attribute must be callable")
        return _coerce_standard_module(module_factory(), path)

    if hasattr(python_module, "exports"):
        return _module_from_exports(python_module.exports, path)

    return _module_from_public_callables(python_module, path)


def module() -> StandardModule:
    """``qy.ext.python-modules`` 是 loader-only 扩展，没有可导入模块体。."""
    return StandardModule("qy.ext.python-modules", {})


DESCRIPTOR = ExtensionDescriptor(
    name="qy.ext.python-modules",
    module_name=None,
    version="0.1",
    description="宿主 .py 文件模块加载扩展（host-python-modules capability）。",
    capabilities=(ExtensionCapability("host-python-modules", "把宿主 .py 文件作为 Qy 模块装载"),),
    bindings=(
        ExtensionBinding(
            "py-module-file",
            kind="value",
            doc="通过 import 路径加载 .py 模块文件。",
            capabilities=("host-python-modules",),
        ),
    ),
)

register_extension(DESCRIPTOR, module)
register_file_module_loader(".py", load_python_file_module)
