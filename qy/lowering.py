# coding: utf-8
# QY_DELETE_AFTER_MIGRATION: target=qy/passes/* staged pipeline
"""HIR lowering pass (re-export shim).

Use ``from qy.passes import lower`` for the lowering API.
This file is kept for backward compatibility.
"""

from __future__ import annotations

from qy.passes.lower_hir import LoweringContext  # noqa: F401
from qy.passes.lower_hir import Scope  # noqa: F401
from qy.passes.lower_hir import lower  # noqa: F401
from qy.passes.lower_hir import lower_source  # noqa: F401
