# coding: utf-8
"""测试 qy.bytecode 和 qy.operator_signature 模块的边界情况。."""

from __future__ import annotations

from qy.backend.vm.bytecode import BytecodeFunction
from qy.backend.vm.bytecode import BytecodeProgram
from qy.backend.vm.bytecode import Instruction
from qy.backend.vm.bytecode import dump_bytecode
from qy.core.operator_signature import Arity
from qy.core.operator_signature import OperatorSignature
from qy.core.operator_signature import format_arity_message
from qy.reader import Symbol


def test_dump_bytecode_with_empty_function():
    """测试格式化包含空函数的字节码程序。."""
    empty_func = BytecodeFunction(
        name=Symbol("empty"),
        params=(),
        register_count=0,
        instructions=(),
    )
    program = BytecodeProgram(
        functions=(empty_func,),
        diagnostics=(),
    )

    formatted = dump_bytecode(program)
    assert "empty" in formatted
    assert "; no instructions" in formatted


def test_dump_bytecode_with_instruction_without_operands():
    """测试格式化没有操作数的指令。."""
    instruction = Instruction(opcode="RETURN", operands=())
    func = BytecodeFunction(
        name=Symbol("test"),
        params=(),
        register_count=0,
        instructions=(instruction,),
    )
    program = BytecodeProgram(
        functions=(func,),
        diagnostics=(),
    )

    formatted = dump_bytecode(program)
    assert "RETURN" in formatted
    # 确保没有多余的逗号或空格
    assert "RETURN," not in formatted


def test_format_arity_message_at_least():
    """测试格式化"至少 N 个参数"的错误消息。."""
    signature = OperatorSignature(arity=Arity(min=2, max=None), return_type="any")
    message = format_arity_message("test-op", signature, 1)
    assert "at least 2 arguments" in message
    assert "got 1" in message


def test_format_arity_message_exactly():
    """测试格式化"恰好 N 个参数"的错误消息。."""
    signature = OperatorSignature(arity=Arity(min=3, max=3), return_type="any")
    message = format_arity_message("test-op", signature, 2)
    assert "exactly 3 arguments" in message
    assert "got 2" in message
