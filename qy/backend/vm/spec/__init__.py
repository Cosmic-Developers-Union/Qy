# coding: utf-8
"""VM 规格：稳定的虚拟机目标规范。.

目标：
- 定义稳定 VM 规格，包括 bytecode、opcode、operand schema
- 规定 ABI、abstract state、effect/continuation protocol
- 作为 LIR 降低和 VM 实现之间的契约

当前：
- 占位包，等待从 qy/bytecode.py 迁移
- 实际 bytecode/opcode/spec 仍散落在 bytecode.py、register_vm.py、lir.py

禁止：
- 不得依赖某个 Python VM instance
- 不得包含具体的执行逻辑
- 不得混入优化策略或实现细节
"""
