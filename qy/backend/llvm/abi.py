# coding: utf-8
"""Qy ABI — Application Binary Interface for the LLVM backend.

Defines:
    - Qy value layout (tagged 64-bit union)
    - Builtin operator index mapping
    - Calling convention
    - Symbol naming rules
"""

from __future__ import annotations

from qy.core.operator_builtins import BUILTIN_OPERATORS

__all__ = [
    "BUILTIN_NAMES",
    "BUILTIN_OPS",
    "NUM_BUILTINS",
    "QY_TAG_CONS",
    "QY_TAG_EFFECT",
    "QY_TAG_FUNCTION",
    "QY_TAG_HOST",
    "QY_TAG_INT",
    "QY_TAG_NIL",
    "QY_TAG_STRING",
    "QY_TAG_T",
    "fn_symbol",
    "str_global",
    "sym_global",
]

# ---------------------------------------------------------------------------
# Tag values — must match qy.h / runtime.c
# ---------------------------------------------------------------------------

QY_TAG_NIL = 0
QY_TAG_T = 1
QY_TAG_INT = 2
QY_TAG_CONS = 3
QY_TAG_FUNCTION = 4
QY_TAG_EFFECT = 5
QY_TAG_HOST = 6
QY_TAG_STRING = 7

# ---------------------------------------------------------------------------
# Builtin operator index — must match libqy/src/runtime.c _builtin_dispatch
# ---------------------------------------------------------------------------
# Mapping: Qy name -> (mqr_runtime_fn, arg_count)
# 事实源在 qy/core/operator_builtins.py；顺序即 mqr_builtin_fn(i64 idx) 的下标。
BUILTIN_OPS: dict[str, tuple[str, int]] = {
    operator.name: (operator.runtime_symbol, operator.arity) for operator in BUILTIN_OPERATORS
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


def _sanitize_global_suffix(name: str) -> str:
    """把任意 symbol 拼写变成合法 LLVM 标识符片段。.

    全局名只是标识符；symbol 原文仍存进数据段（``qy_resolve_sym`` 用它解析）。
    非 ``[A-Za-z0-9_.]`` 的字符按 ``_xx`` 十六进制转义，避免 ``=`` / ``"`` 等
    让 LLVM IR 非法，也避免不同符号坍缩到同一标识符。
    """
    return "".join(ch if (ch.isalnum() or ch in "_.") else f"_{ord(ch):02x}" for ch in name)


def sym_global(fn_idx: int, pc: int, sym: str) -> str:
    """Global name for a symbol string at (fn_idx, pc, sym)."""
    return f"@.sym.fn{fn_idx}.pc{pc}.{_sanitize_global_suffix(sym)}"
