# coding: utf-8
"""Qy LLVM backend — compiles LIR to a native executable.

Pipeline:
    LIRProgram -> emit() -> .ll -> llc -> .o -> clang/gcc link -> a.out

Public API:
    emit(lir_program)         -> str (LLVM IR text)
    compile_to_llvm_text(lir) -> str (alias for emit)
    link(ll_text, ...)        -> CompileResult

Example:
    from qy import lower, lower_mir, lower_lir, read
    from qy.backend.llvm import emit, link

    forms = list(read('(echo "hello, world!")'))
    lir = lower(forms)
    lir = lower_mir(lir)
    lir = lower_lir(lir)

    result = link(emit(lir), output_name="hello")
    print(result.executable)
"""

from __future__ import annotations

from qy.backend.llvm.abi import (
    BUILTIN_NAMES,
    BUILTIN_OPS,
    NUM_BUILTINS,
    QY_TAG_CONS,
    QY_TAG_EFFECT,
    QY_TAG_FUNCTION,
    QY_TAG_HOST,
    QY_TAG_INT,
    QY_TAG_NIL,
    QY_TAG_STRING,
    QY_TAG_T,
    builtin_index,
    fn_symbol,
    sym_global,
    str_global,
)
from qy.backend.llvm.emit import compile_to_llvm_text
from qy.backend.llvm.emit import emit
from qy.backend.llvm.link import CompilationError
from qy.backend.llvm.link import CompileResult
from qy.backend.llvm.link import link

__all__ = [
    # ABI
    "QY_TAG_NIL",
    "QY_TAG_T",
    "QY_TAG_INT",
    "QY_TAG_CONS",
    "QY_TAG_FUNCTION",
    "QY_TAG_EFFECT",
    "QY_TAG_HOST",
    "QY_TAG_STRING",
    "BUILTIN_NAMES",
    "BUILTIN_OPS",
    "NUM_BUILTINS",
    "builtin_index",
    "fn_symbol",
    "str_global",
    "sym_global",
    # Emit
    "emit",
    "compile_to_llvm_text",
    # Link
    "link",
    "CompileResult",
    "CompilationError",
]