# coding: utf-8
# QY_MIGRATION_COMPLETE: migrated to qy/vm/instance/machine.py
# This file now re-exports from the new location for backward compatibility.

"""Register-based virtual machine (backward compatibility layer).

This module re-exports RegisterVirtualMachine and related functions from
their new location at qy.vm.instance.machine for backward compatibility.

New code should import from qy.vm.instance.machine directly.
"""

from __future__ import annotations

from qy.vm.instance.machine import RegisterVirtualMachine
from qy.vm.instance.machine import call_function_value
from qy.vm.instance.machine import evaluate_bytecode
from qy.vm.instance.machine import evaluate_bytecode_async
from qy.vm.instance.machine import evaluate_bytecode_source
from qy.vm.instance.machine import evaluate_bytecode_source_async

__all__ = [
    "RegisterVirtualMachine",
    "call_function_value",
    "evaluate_bytecode",
    "evaluate_bytecode_async",
    "evaluate_bytecode_source",
    "evaluate_bytecode_source_async",
]
