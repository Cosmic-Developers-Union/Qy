# coding: utf-8
"""Compatibility imports for the old ``qy.stdlib`` path."""

from qy.std import LANGUAGE_CORE_MODULES
from qy.std import OPTIONAL_STDLIB_MODULES
from qy.std import PRELUDE_MODULES
from qy.std import STANDARD_PROFILE_MODULES
from qy.std import StandardModule
from qy.std import load_module
from qy.std import load_module_async
from qy.std import module_names
from qy.std import register_module
from qy.std import register_module_loader
from qy.std import standard_bindings
from qy.std import standard_profile_bindings

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
