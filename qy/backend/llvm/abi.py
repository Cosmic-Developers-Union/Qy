# coding: utf-8
"""Qy ABI — Application Binary Interface for the LLVM backend.

Defines:
    - Qy value layout (tagged 64-bit union)
    - Builtin operator index mapping
    - Calling convention
    - Symbol naming rules
"""

from __future__ import annotations

__all__ = [
    "QY_TAG_NIL",
    "QY_TAG_T",
    "QY_TAG_INT",
    "QY_TAG_CONS",
    "QY_TAG_FUNCTION",
    "QY_TAG_EFFECT",
    "QY_TAG_HOST",
    "QY_TAG_STRING",
    "BUILTIN_OPS",
    "BUILTIN_NAMES",
    "NUM_BUILTINS",
    "fn_symbol",
    "str_global",
    "sym_global",
]

# ---------------------------------------------------------------------------
# Tag values — must match qy.h / runtime.c
# ---------------------------------------------------------------------------

QY_TAG_NIL      = 0
QY_TAG_T        = 1
QY_TAG_INT      = 2
QY_TAG_CONS     = 3
QY_TAG_FUNCTION = 4
QY_TAG_EFFECT   = 5
QY_TAG_HOST     = 6
QY_TAG_STRING   = 7

# ---------------------------------------------------------------------------
# Builtin operator index — must match libqy/src/runtime.c _builtin_dispatch
# ---------------------------------------------------------------------------
# Mapping: Qy name -> (mqr_runtime_fn, arg_count)
# Order determines index! Index is used in mqr_builtin_fn(i64 idx) at runtime.

BUILTIN_OPS: dict[str, tuple[str, int]] = {
    "+":       ("mqr_add",    2),
    "-":       ("mqr_sub",    2),
    "*":       ("mqr_mul",    2),
    "/":       ("mqr_div",    2),
    "=":       ("mqr_eq",     2),
    "eq":      ("mqr_eq",     2),
    "<":       ("mqr_lt",     2),
    ">":       ("mqr_gt",     2),
    "display": ("mqr_display", 1),
    "echo":    ("mqr_echo",   1),
    "newline": ("mqr_newline", 0),
    "read":    ("mqr_read",   0),
    "read-int":("mqr_read_int", 0),
    "cons":    ("mqr_cons",   2),
    "car":     ("mqr_car",    1),
    "cdr":     ("mqr_cdr",    1),
    "nil?":    ("mqr_nil_p",  1),
    "not":     ("mqr_not",    1),
}

BUILTIN_NAMES: list[str] = list(BUILTIN_OPS.keys())
NUM_BUILTINS: int = len(BUILTIN_NAMES)

# Verify index lookup
def builtin_index(name: str) -> int:
    return BUILTIN_NAMES.index(name)


# ---------------------------------------------------------------------------
# Symbol naming — must match the C wrapper in libqy
# ---------------------------------------------------------------------------

def fn_symbol(fn_idx: int) -> str:
    """LLVM IR function name for Qy function at index fn_idx."""
    return f"qy_fn_{fn_idx}"


def str_global(fn_idx: int, pc: int) -> str:
    """Global name for a string constant at (fn_idx, pc)."""
    return f"@.str.fn{fn_idx}.pc{pc}"


def sym_global(fn_idx: int, pc: int, sym: str) -> str:
    """Global name for a symbol string at (fn_idx, pc, sym)."""
    safe = sym.replace("-", "_").replace("?", "_p")
    return f"@.sym.fn{fn_idx}.pc{pc}.{safe}"