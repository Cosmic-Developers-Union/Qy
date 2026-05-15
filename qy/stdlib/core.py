# coding: utf-8

from __future__ import annotations

from qy.stdlib.arithmetic import operators as arithmetic_operators
from qy.stdlib.control import operators as control_operators
from qy.stdlib.data import operators as chain_operators
from qy.stdlib.effects import operators as effects_operators
from qy.stdlib.module import StandardModule
from qy.stdlib.modules import operators as modules_operators


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
