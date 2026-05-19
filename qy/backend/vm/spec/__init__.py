# coding: utf-8
"""VM backend spec 目标包。

目标：
- 描述 Qy Register VM target 的稳定规格：bytecode、opcode、ABI、状态机、frame、effect/continuation 协议。
- 作为 LIR -> VM bytecode、Python VM implementation、LLVM/libqy 验证的共同契约。

当前：
- 占位包；实际 bytecode/opcode/spec 仍散落在 `qy/bytecode.py`、`qy/register_vm.py`、`qy/lir.py`。

禁止：
- 不得依赖 `qy/vm` 中的 Python VM instance 可变运行状态。
- 不得把 Python 实现细节写成 VM target 规格。
"""

