# coding: utf-8
"""VM 实例：一次执行的可变运行实例。.

目标：
- 实现一次执行的可变运行实例
- 包括 machine、runtime frame、runtime state、scheduler、host adapter

当前：
- RegisterVirtualMachine 已从 qy/register_vm.py 迁移到此处
- values.py 提供 VM 特定的运行时值（HostObjectRef、TailCall）

禁止：
- 只能实现 backend/vm/spec，不得定义 opcode/ABI 规格
- 不得引入第二执行后端
"""

from qy.vm.instance.frame import CapturedFrame
from qy.vm.instance.frame import FunctionFrame
from qy.vm.instance.frame import VirtualStackFrame
from qy.vm.instance.host import HostAdapter
from qy.vm.instance.host import HostCallable
from qy.vm.instance.machine import RegisterVirtualMachine
from qy.vm.instance.machine import call_function_value
from qy.vm.instance.machine import evaluate_bytecode
from qy.vm.instance.machine import evaluate_bytecode_async
from qy.vm.instance.machine import evaluate_bytecode_source
from qy.vm.instance.machine import evaluate_bytecode_source_async
from qy.vm.instance.scheduler import ScheduledTask
from qy.vm.instance.scheduler import TaskState
from qy.vm.instance.state import ExecutionState
from qy.vm.instance.state import VirtualStack
from qy.vm.instance.values import HostObjectRef
from qy.vm.instance.values import TailCall

__all__ = [
    "CapturedFrame",
    "ExecutionState",
    "FunctionFrame",
    "HostAdapter",
    "HostCallable",
    "HostObjectRef",
    "RegisterVirtualMachine",
    "ScheduledTask",
    "TailCall",
    "TaskState",
    "VirtualStack",
    "VirtualStackFrame",
    "call_function_value",
    "evaluate_bytecode",
    "evaluate_bytecode_async",
    "evaluate_bytecode_source",
    "evaluate_bytecode_source_async",
]
