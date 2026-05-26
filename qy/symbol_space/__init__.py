# coding: utf-8
"""内置符号空间 (symbol-space) 实现。.

每个内置符号空间对应一个 Python 子模块；它们既参与 pre-ssc 的搭建
（``lisp-ss``, ``number-ss``, ``char-ss``, ``string-ss`` 在
``qy.session.pre_ss`` 中由这里的 binding 函数提供），也以可显式
``(from qy.X import …)`` 的模块形式暴露。

模块加载注册表本身住在 ``qy.import_.registry``；本包在 import-time 把
内置 loader 注册过去。
"""

from __future__ import annotations

from qy.import_.module import StandardModule
from qy.import_.registry import register_default_module_loader
from qy.import_.registry import standard_profile_bindings as _standard_profile_bindings

__all__ = [
    "LANGUAGE_CORE_MODULES",
    "OPTIONAL_STDLIB_MODULES",
    "PRELUDE_MODULES",
    "STANDARD_PROFILE_MODULES",
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


def standard_profile_bindings(modules=STANDARD_PROFILE_MODULES):
    return _standard_profile_bindings(modules)


def _load_core_module() -> StandardModule:
    from qy.symbol_space.core import module

    return module()


def _load_io_module() -> StandardModule:
    from qy.symbol_space.io import module

    return module()


def _load_num_module() -> StandardModule:
    """``qy.num`` 模块：number-ss 算子的可显式 import 形态。.

    与 number-ss 共享同一份 bindings 来源 (``number_ss_bindings``)。
    """
    from qy.session.number_ops import number_ss_bindings

    return StandardModule("qy.num", number_ss_bindings())


def _load_string_module() -> StandardModule:
    from qy.symbol_space.strings import module

    return module()


def _load_char_module() -> StandardModule:
    from qy.symbol_space.chars import module

    return module()


def _load_py_module() -> StandardModule:
    from qy.symbol_space.python import operators as python_operators

    return StandardModule("qy.py", python_operators())


def _load_legacy_module() -> StandardModule:
    from qy.symbol_space.control import legacy_operators as control_legacy
    from qy.symbol_space.effects import legacy_operators as effects_legacy

    return StandardModule("qy.legacy", {**control_legacy(), **effects_legacy()})


def _load_testhost_module() -> StandardModule:
    from qy.symbol_space.testhost import module

    return module()


def _load_int8_module() -> StandardModule:
    from qy.symbol_space.numeric_spaces import make_int8_space

    return make_int8_space()


def _load_int16_module() -> StandardModule:
    from qy.symbol_space.numeric_spaces import make_int16_space

    return make_int16_space()


def _load_int32_module() -> StandardModule:
    from qy.symbol_space.numeric_spaces import make_int32_space

    return make_int32_space()


def _load_int64_module() -> StandardModule:
    from qy.symbol_space.numeric_spaces import make_int64_space

    return make_int64_space()


def _load_uint8_module() -> StandardModule:
    from qy.symbol_space.numeric_spaces import make_uint8_space

    return make_uint8_space()


def _load_uint16_module() -> StandardModule:
    from qy.symbol_space.numeric_spaces import make_uint16_space

    return make_uint16_space()


def _load_uint32_module() -> StandardModule:
    from qy.symbol_space.numeric_spaces import make_uint32_space

    return make_uint32_space()


def _load_uint64_module() -> StandardModule:
    from qy.symbol_space.numeric_spaces import make_uint64_space

    return make_uint64_space()


def _load_float16_module() -> StandardModule:
    from qy.symbol_space.numeric_spaces import make_float16_space

    return make_float16_space()


def _load_float32_module() -> StandardModule:
    from qy.symbol_space.numeric_spaces import make_float32_space

    return make_float32_space()


def _load_float64_module() -> StandardModule:
    from qy.symbol_space.numeric_spaces import make_float64_space

    return make_float64_space()


def _load_float128_module() -> StandardModule:
    from qy.symbol_space.numeric_spaces import make_float128_space

    return make_float128_space()


def _install_builtin_loaders() -> None:
    register_default_module_loader("qy.core", _load_core_module)
    register_default_module_loader("qy.io", _load_io_module)
    register_default_module_loader("qy.num", _load_num_module)
    register_default_module_loader("qy.str", _load_string_module)
    register_default_module_loader("qy.char", _load_char_module)
    register_default_module_loader("qy.py", _load_py_module)
    register_default_module_loader("qy.testhost", _load_testhost_module)
    register_default_module_loader("qy.legacy", _load_legacy_module)
    register_default_module_loader("qy.int8", _load_int8_module)
    register_default_module_loader("qy.int16", _load_int16_module)
    register_default_module_loader("qy.int32", _load_int32_module)
    register_default_module_loader("qy.int64", _load_int64_module)
    register_default_module_loader("qy.uint8", _load_uint8_module)
    register_default_module_loader("qy.uint16", _load_uint16_module)
    register_default_module_loader("qy.uint32", _load_uint32_module)
    register_default_module_loader("qy.uint64", _load_uint64_module)
    register_default_module_loader("qy.float16", _load_float16_module)
    register_default_module_loader("qy.float32", _load_float32_module)
    register_default_module_loader("qy.float64", _load_float64_module)
    register_default_module_loader("qy.float128", _load_float128_module)


_install_builtin_loaders()
