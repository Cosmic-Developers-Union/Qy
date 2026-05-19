# coding: utf-8
# QY_DELETE_AFTER_MIGRATION: target=qy/ir/mir/__init__.py
"""MIR models (re-export shim).

Use ``from qy.ir import MIRProgram, ...`` for all MIR model imports.
This file is kept for backward compatibility.
"""

from __future__ import annotations

from qy.ir.mir import *  # noqa: F401, F403
from qy.ir.mir import __all__  # noqa: F401
