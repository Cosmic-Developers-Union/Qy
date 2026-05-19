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

from qy.backend.llvm.abi import BUILTIN_NAMES
from qy.backend.llvm.abi import BUILTIN_OPS
from qy.backend.llvm.abi import NUM_BUILTINS
from qy.backend.llvm.abi import QY_TAG_CONS
from qy.backend.llvm.abi import QY_TAG_EFFECT
from qy.backend.llvm.abi import QY_TAG_FUNCTION
from qy.backend.llvm.abi import QY_TAG_HOST
from qy.backend.llvm.abi import QY_TAG_INT
from qy.backend.llvm.abi import QY_TAG_NIL
from qy.backend.llvm.abi import QY_TAG_STRING
from qy.backend.llvm.abi import QY_TAG_T
from qy.backend.llvm.abi import builtin_index
from qy.backend.llvm.abi import fn_symbol
from qy.backend.llvm.abi import str_global
from qy.backend.llvm.abi import sym_global
from qy.backend.llvm.emit import compile_to_llvm_text
from qy.backend.llvm.emit import emit
from qy.backend.llvm.link import CompilationError
from qy.backend.llvm.link import CompileResult
from qy.backend.llvm.link import link

__all__ = [
    "BUILTIN_NAMES",
    "BUILTIN_OPS",
    "NUM_BUILTINS",
    "QY_TAG_CONS",
    "QY_TAG_EFFECT",
    "QY_TAG_FUNCTION",
    "QY_TAG_HOST",
    "QY_TAG_INT",
    # ABI
    "QY_TAG_NIL",
    "QY_TAG_STRING",
    "QY_TAG_T",
    "CompilationError",
    "CompileResult",
    "builtin_index",
    "compile_to_llvm_text",
    # Emit
    "emit",
    "fn_symbol",
    # Link
    "link",
    "str_global",
    "sym_global",
]
