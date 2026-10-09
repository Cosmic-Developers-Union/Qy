# coding: utf-8
"""Qy 扩展机制与宿主边界测试。.

验证：
- 内核包不直接依赖宿主扩展（``qy.ext`` / 已迁移的宿主模块）；
- 宿主能力只能通过 ``qy.ext.*`` 声明的扩展进入语言；
- ``HostReference`` 属于语义层（``qy.sem.host``），VM 只重导出；
- ``qy.core`` 不再混入宿主 Python 算子。
"""

from __future__ import annotations

import ast
from pathlib import Path

from qy.ext import ExtensionPolicy
from qy.ext import extension_names
from qy.ext import extension_requires
from qy.ext import get_extension
from qy.ext import load_extension
from qy.import_.registry import load_module
from qy.sem.host import HostReference
from qy.session.runtime_space import create_standard_runtime_space as standard_environment

ROOT = Path(__file__).resolve().parents[1]

KERNEL_PACKAGES = (
    "qy/core",
    "qy/frontend",
    "qy/ir",
    "qy/analysis",
    "qy/backend/vm/spec",
)

FORBIDDEN_KERNEL_IMPORTS = (
    "qy.ext",
    "qy.std.python",
    "qy.std.testhost",
)


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_kernel_packages_do_not_import_host_extensions():
    for package in KERNEL_PACKAGES:
        directory = ROOT / package
        for path in directory.rglob("*.py"):
            imported = _imported_modules(path)
            violations = sorted(
                name
                for name in imported
                if any(
                    name == forbidden or name.startswith(forbidden + ".")
                    for forbidden in FORBIDDEN_KERNEL_IMPORTS
                )
            )
            assert not violations, f"{path} imports host extension modules: {violations}"


def test_builtin_extensions_are_declared_with_capabilities():
    names = extension_names()
    assert "qy.ext.python" in names
    assert "qy.ext.fs" in names
    assert "qy.ext.testhost" in names
    assert "qy.ext.python-modules" in names
    assert "qy.ext.interp" in names

    python_ext = get_extension("qy.ext.python")
    assert python_ext.module_name == "qy.py"
    assert [capability.name for capability in python_ext.capabilities] == ["python-exec"]
    assert [binding.name for binding in python_ext.bindings] == ["py"]

    fs_ext = get_extension("qy.ext.fs")
    assert fs_ext.module_name == "qy.ext.fs"
    assert [binding.name for binding in fs_ext.bindings] == ["read-file"]
    assert {capability.name for capability in fs_ext.capabilities} == {"filesystem"}

    interp_ext = get_extension("qy.ext.interp")
    assert interp_ext.module_name == "qy.ext.interp"
    assert {binding.name for binding in interp_ext.bindings} == {
        "cli-args",
        "lookup-export",
        "display",
        "raise-error",
        "gensym",
    }
    assert {capability.name for capability in interp_ext.capabilities} == {
        "cli",
        "introspection",
        "symbols",
    }

    host_modules = get_extension("qy.ext.python-modules")
    assert host_modules.module_name is None
    assert {capability.name for capability in host_modules.capabilities} == {"host-python-modules"}


def test_extension_modules_load_through_registry():
    module = load_extension("qy.ext.fs")
    assert module.name == "qy.ext.fs"
    assert {symbol.name for symbol in module.exports} == {"read-file"}

    py_module = load_module("qy.py")
    assert "py" in {symbol.name for symbol in py_module.exports}


def test_qy_core_has_no_host_python_operators():
    env = standard_environment()
    module = load_module("qy.core")
    names = {symbol.name for symbol in module.exports}
    assert "py" not in names
    # container constructors stay in core: they produce Qy semantic values.
    assert {"tuple", "list", "dict", "set"} <= names
    del env


def test_read_file_lives_in_fs_extension_not_io():
    env = standard_environment()
    for symbol, value in load_module("qy.io").exports.items():
        env.define(symbol, value)
    assert {symbol.name for symbol in load_module("qy.io").exports} == {
        "print",
        "echo",
        "display",
        "newline",
    }

    from qy.runtime import evaluate_source

    evaluate_source("(from qy.ext.fs import read-file)", env)
    assert "read-file" in {symbol.name for symbol in env.bindings()}


def test_host_reference_is_a_semantic_value():
    reference = HostReference({"a": 1})
    assert reference.value == {"a": 1}


def test_python_file_modules_load_through_extension_hook(tmp_path: Path):
    module_file = tmp_path / "host_mod.py"
    module_file.write_text("exports = {'answer': 42}\n", encoding="utf-8")

    from qy.import_.registry import load_file_module

    module = load_file_module(str(module_file))
    names = {symbol.name for symbol in module.exports}
    assert names == {"answer"}


def test_extension_policy_gates_loading():
    import pytest

    from qy.errors import QyCapabilityError

    assert extension_requires("qy.ext.fs") == ("filesystem",)
    assert set(extension_requires("qy.ext.python")) == {"python-exec"}

    with pytest.raises(QyCapabilityError, match="not enabled"):
        load_extension("qy.ext.fs", policy=ExtensionPolicy(enabled_extensions=frozenset()))

    with pytest.raises(QyCapabilityError, match="filesystem"):
        load_extension("qy.ext.fs", policy=ExtensionPolicy(allowed_capabilities=frozenset()))

    module = load_extension(
        "qy.ext.fs",
        policy=ExtensionPolicy(
            enabled_extensions=frozenset({"qy.ext.fs"}),
            allowed_capabilities=frozenset({"filesystem"}),
        ),
    )
    assert module.name == "qy.ext.fs"

    # no policy -> unrestricted (existing explicit-import behavior)
    assert load_extension("qy.ext.fs").name == "qy.ext.fs"
