# coding: utf-8
# QY_DELETE_AFTER_MIGRATION: target=qy/ir/__init__.py
"""HIR models (re-export shim).

Use ``from qy.ir import ...`` for all IR model imports.
This file is kept for backward compatibility.
"""

from __future__ import annotations

from qy.ir.hir import *  # noqa: F401, F403
from qy.ir.hir import __all__  # noqa: F401
