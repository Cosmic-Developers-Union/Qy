# coding: utf-8
# QY_DELETE_AFTER_MIGRATION: target=qy/core/__init__.py
"""Operator type declarations.

The canonical source of OperatorKind / TypeName is now qy/core/__init__.py.
All internal imports should use `from qy.core import OperatorKind, TypeName`.

NOTE: qy/types.py shadows Python stdlib `types` — this file must not use
any top-level import that triggers stdlib `types` resolution at load time.
Use __getattr__ for lazy access to types defined in qy/core.
"""

from __future__ import annotations

__all__ = ["OperatorKind", "TypeName"]  # noqa: F822

# Module-global cache for the stdlib types module — filled on first
# successful retrieval so subsequent calls never re-trigger import.
_STDLIB_TYPES = None


def __getattr__(name: str):
    global _STDLIB_TYPES

    if name in ("OperatorKind", "TypeName"):
        from qy._types import _TYPES

        return getattr(_TYPES, name)

    # Retrieve the real stdlib types module from sys.modules.
    # It may already be there (normal import path) or may be qy/types.py
    # itself (console-script path — qy/types.py was loaded as "types").
    # In the latter case, we must import the stdlib types by absolute path.
    import sys

    candidate = sys.modules.get("types")

    if candidate is None:
        raise AttributeError(name)

    # If the candidate is qy/types.py itself (happens when this file was
    # loaded as "types" by Python's import machinery), fall back to the
    # stdlib by absolute path.  We detect this by checking __file__.
    candidate_file = getattr(candidate, "__file__", "") or ""
    if "qy" + chr(47) + "types.py" in candidate_file or candidate_file.endswith("qy/types.py"):
        import importlib.util

        # Use the same mechanism as `importlib.import_module` but with
        # absolute filesystem path so we never go through qy/types.py.
        stdlib_paths = sys.path  # already contains stdlib paths
        for sp in stdlib_paths:
            p = sp + "/types.py"
            import os

            if os.path.isfile(p):
                spec = importlib.util.spec_from_file_location("types", p)
                if spec is not None and spec.loader is not None:
                    stdlib_types = importlib.util.module_from_spec(spec)
                    sys.modules["types"] = stdlib_types
                    _STDLIB_TYPES = stdlib_types
                    spec.loader.exec_module(stdlib_types)
                    return getattr(stdlib_types, name)

    # Normal case: stdlib types already in sys.modules.
    _STDLIB_TYPES = candidate
    return getattr(candidate, name)
