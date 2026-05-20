# coding: utf-8
"""VM 规格：稳定的虚拟机目标规范。.

目标：
- 定义稳定 VM 规格，包括 bytecode、opcode、operand schema
- 规定 ABI、abstract state、effect/continuation protocol
- 作为 LIR 降低和 VM 实现之间的契约

当前：
- 从 qy/bytecode.py 迁移核心规格定义
- 提供完整的 VM target 规格，包括 opcode、bytecode、ABI、state、effect

禁止：
- 不得依赖某个 Python VM instance
- 不得包含具体的执行逻辑
- 不得混入优化策略或实现细节
"""

from qy.backend.vm.spec.abi import CallConvention
from qy.backend.vm.spec.abi import FrameLayout
from qy.backend.vm.spec.abi import RegisterAllocation
from qy.backend.vm.spec.bytecode import FunctionSpec
from qy.backend.vm.spec.bytecode import Instruction
from qy.backend.vm.spec.bytecode import ProgramSpec
from qy.backend.vm.spec.bytecode import Register
from qy.backend.vm.spec.effect import ContinuationSpec
from qy.backend.vm.spec.effect import EffectProtocol
from qy.backend.vm.spec.effect import HandlerSpec
from qy.backend.vm.spec.opcode import OPCODE_TABLE
from qy.backend.vm.spec.opcode import Opcode
from qy.backend.vm.spec.opcode import OpcodeInfo
from qy.backend.vm.spec.state import AbstractVMState
from qy.backend.vm.spec.state import FrameState
from qy.backend.vm.spec.state import VMState

__all__ = [
    "OPCODE_TABLE",
    "AbstractVMState",
    # abi
    "CallConvention",
    "ContinuationSpec",
    # effect
    "EffectProtocol",
    "FrameLayout",
    "FrameState",
    "FunctionSpec",
    "HandlerSpec",
    "Instruction",
    # opcode
    "Opcode",
    "OpcodeInfo",
    "ProgramSpec",
    # bytecode
    "Register",
    "RegisterAllocation",
    # state
    "VMState",
]
