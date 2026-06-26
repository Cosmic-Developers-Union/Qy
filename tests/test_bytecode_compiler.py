# coding: utf-8
"""测试 qy.backend.vm.compiler 模块。."""

from __future__ import annotations

import pytest

from qy.backend.vm.compiler import _lir_to_bytecode_opcode


def test_lir_to_bytecode_opcode_load_nil():
    """测试 LOAD_NIL 转换。."""
    assert _lir_to_bytecode_opcode("LOAD_NIL") == "LOAD_HOST"


def test_lir_to_bytecode_opcode_load_t():
    """测试 LOAD_T 转换。."""
    assert _lir_to_bytecode_opcode("LOAD_T") == "LOAD_HOST"


def test_lir_to_bytecode_opcode_branch_nil():
    """测试 BRANCH_NIL 转换。."""
    assert _lir_to_bytecode_opcode("BRANCH_NIL") == "JUMP_IF_FALSE"


def test_lir_to_bytecode_opcode_passthrough():
    """测试其他操作码直接传递。."""
    assert _lir_to_bytecode_opcode("CALL") == "CALL"
    assert _lir_to_bytecode_opcode("RETURN") == "RETURN"


def test_lir_to_bytecode_opcode_rejects_non_bytecode_opcode():
    """Compat LIR 不能把 MIR-only opcode 静默塞进 bytecode。."""
    with pytest.raises(ValueError, match="unsupported compat LIR opcode"):
        _lir_to_bytecode_opcode("LOAD_CONST")
