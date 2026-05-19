# coding: utf-8
"""LIR models (re-export shim).

Use ``from qy.ir import LIRProgram, ...`` for all LIR model imports.
This file is kept for backward compatibility.
"""

from __future__ import annotations

from qy.ir.lir import *  # noqa: F401, F403
from qy.ir.lir import __all__  # noqa: F401