# coding: utf-8
"""WebAssembly backend: LIR -> WAT.

目标：把 register-VM 的 LIR（compat dialect）降到 WebAssembly text，供
``wat2wasm`` 汇编、Node 的 WebAssembly 引擎执行。

当前：支持 int/nil/T/string、内建算术/比较、无自由变量的 defun/lambda、
let、cond/pipeline 控制流、CALL/TAIL_CALL（无尾调用优化）。effect、module、
macro、并行、闭包捕获、cons 等尚未支持，遇到时会抛
:class:`WasmUnsupportedError`。

禁止：不得在此定义 LIR/opcode 规格；VM target 规格在
``qy/backend/vm/spec``。
"""

from __future__ import annotations

from qy.backend.wasm.abi import BUILTIN_NAMES as BUILTIN_NAMES
from qy.backend.wasm.abi import NUM_BUILTINS as NUM_BUILTINS
from qy.backend.wasm.emit import WasmUnsupportedError as WasmUnsupportedError
from qy.backend.wasm.emit import emit as emit

__all__ = ["BUILTIN_NAMES", "NUM_BUILTINS", "WasmUnsupportedError", "emit"]
