# coding: utf-8

from __future__ import annotations

from typing import TYPE_CHECKING
from typing import Any

__all__ = [
    "CompileTimeEnvironment",
    "compile_time_binding_names",
    "compile_time_environment",
]

if TYPE_CHECKING:
    from qy.evaluator import Environment

    type CompileTimeEnvironment = Environment
else:
    CompileTimeEnvironment = Any


def compile_time_environment(env: Environment) -> CompileTimeEnvironment:
    return env


def compile_time_binding_names(env: CompileTimeEnvironment) -> tuple[str, ...]:
    return tuple(sorted({symbol.name for symbol in env.bindings()} | {"capture", "gensym"}))
