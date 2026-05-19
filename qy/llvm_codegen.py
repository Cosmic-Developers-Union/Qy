# coding: utf-8
# QY_DELETE_AFTER_MIGRATION: target=qy/backend/llvm/*
"""LLVM codegen — thin shim that re-exports the new backend.

This file is kept for backward compatibility. New code should use:
    from qy.backend.llvm import emit, link
"""

from __future__ import annotations

# Re-export from the new backend location
from qy.backend.llvm.emit import compile_to_llvm_text
from qy.backend.llvm.emit import emit as emit_llvm_module

__all__ = [
    "compile_to_llvm_text",
    "emit_llvm_module",
]
