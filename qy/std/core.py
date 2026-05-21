# coding: utf-8

from __future__ import annotations

from qy.std.arithmetic import operators as arithmetic_operators
from qy.std.control import operators as control_operators
from qy.std.data import operators as chain_operators
from qy.std.effects import operators as effects_operators
from qy.std.module import StandardModule
from qy.std.modules import operators as modules_operators


def module() -> StandardModule:
    return StandardModule(
        "qy.core",
        {
            **arithmetic_operators(),
            **chain_operators(),
            **control_operators(),
            **effects_operators(),
            **modules_operators(),
        },
    )
