# coding: utf-8
"""Tests for bytecode migration to qy.backend.vm."""

import pytest

from qy.backend.vm import BytecodeFunction
from qy.backend.vm import BytecodeProgram
from qy.backend.vm import Instruction
from qy.backend.vm import deserialize_bytecode
from qy.backend.vm import dump_bytecode
from qy.backend.vm import pretty_print_bytecode
from qy.backend.vm import serialize_bytecode
from qy.reader import Symbol


def test_bytecode_types():
    """Test basic bytecode types."""
    # Create instruction
    inst = Instruction("LOAD_HOST", (0, 42))
    assert inst.opcode == "LOAD_HOST"
    assert inst.operands == (0, 42)
    assert inst.span is None

    # Create function
    func = BytecodeFunction(
        name=Symbol("test"),
        params=(Symbol("x"), Symbol("y")),
        register_count=3,
        instructions=(inst,),
    )
    assert func.name.name == "test"
    assert len(func.params) == 2
    assert func.register_count == 3
    assert len(func.instructions) == 1

    # Create program
    program = BytecodeProgram(functions=(func,), main=0)
    assert len(program.functions) == 1
    assert program.main == 0
    assert program.ok


def test_dump_bytecode():
    """Test bytecode dump."""
    func = BytecodeFunction(
        name=Symbol("main"),
        params=(),
        register_count=2,
        instructions=(
            Instruction("LOAD_HOST", (0, 42)),
            Instruction("RETURN", (0,)),
        ),
    )
    program = BytecodeProgram(functions=(func,), main=0)

    dump = dump_bytecode(program)
    assert "fn#0 main() regs=2 [main]" in dump
    assert "0000: LOAD_HOST 0, 42" in dump
    assert "0001: RETURN 0" in dump


def test_pretty_print_bytecode():
    """Test bytecode pretty print."""
    func = BytecodeFunction(
        name=Symbol("add"),
        params=(Symbol("a"), Symbol("b")),
        register_count=3,
        instructions=(
            Instruction("LOAD_ENV", (0, Symbol("a"))),
            Instruction("LOAD_ENV", (1, Symbol("b"))),
            Instruction("CALL", (2, Symbol("+"), 0, 1)),
            Instruction("RETURN", (2,)),
        ),
    )
    program = BytecodeProgram(functions=(func,), main=0)

    pretty = pretty_print_bytecode(program, show_spans=False)
    assert "Bytecode Program" in pretty
    assert "Function #0: add(a, b) [MAIN]" in pretty
    assert "Registers: 3" in pretty
    assert "Instructions: 4" in pretty
    assert "0000: LOAD_ENV 2, a" in pretty or "0000: LOAD_ENV" in pretty


def test_serialize_deserialize_bytecode():
    """Test bytecode serialization and deserialization."""
    func1 = BytecodeFunction(
        name=Symbol("main"),
        params=(),
        register_count=2,
        instructions=(
            Instruction("LOAD_HOST", (0, 42)),
            Instruction("CALL", (1, Symbol("print"), 0)),
            Instruction("RETURN", (1,)),
        ),
    )
    func2 = BytecodeFunction(
        name=Symbol("helper"),
        params=(Symbol("x"),),
        register_count=2,
        instructions=(
            Instruction("LOAD_ENV", (0, Symbol("x"))),
            Instruction("RETURN", (0,)),
        ),
    )
    program = BytecodeProgram(functions=(func1, func2), main=0)

    # Serialize
    data = serialize_bytecode(program)
    assert isinstance(data, bytes)
    assert data.startswith(b"QY\x00\x01")

    # Deserialize
    restored = deserialize_bytecode(data)
    assert len(restored.functions) == 2
    assert restored.main == 0
    assert restored.functions[0].name.name == "main"
    assert restored.functions[1].name.name == "helper"
    assert len(restored.functions[0].instructions) == 3
    assert len(restored.functions[1].instructions) == 2


def test_serialize_with_diagnostics():
    """Test serialization with diagnostics."""
    from qy.diag import Diagnostic

    func = BytecodeFunction(
        name=Symbol("test"),
        params=(),
        register_count=1,
        instructions=(Instruction("RETURN", (0,)),),
    )
    program = BytecodeProgram(
        functions=(func,),
        main=0,
        diagnostics=(
            Diagnostic("warning message", severity="warning"),
            Diagnostic("error message", severity="error"),
        ),
    )

    data = serialize_bytecode(program)
    restored = deserialize_bytecode(data)

    assert len(restored.diagnostics) == 2
    assert restored.diagnostics[0].severity == "warning"
    assert restored.diagnostics[0].message == "warning message"
    assert restored.diagnostics[1].severity == "error"
    assert restored.diagnostics[1].message == "error message"
    assert not restored.ok


def test_compile_simple_program():
    """Test compiling a simple program."""
    from qy.runtime import Qy

    qy = Qy()
    source = "(define x 42)"

    # Compile through the pipeline
    program_ir = qy.lower(source)
    bytecode_program = qy.compile_bytecode(program_ir)

    assert isinstance(bytecode_program, BytecodeProgram)
    assert bytecode_program.ok
    assert len(bytecode_program.functions) > 0


def test_bytecode_function_value_location():
    """Test that BytecodeFunctionValue is still in qy.bytecode."""
    from qy.bytecode import BytecodeFunctionValue

    # Should be importable from old location
    assert BytecodeFunctionValue is not None


def test_invalid_binary_format():
    """Test deserialization with invalid data."""
    with pytest.raises(ValueError, match="Invalid magic"):
        deserialize_bytecode(b"INVALID")

    with pytest.raises(ValueError, match="Unsupported version"):
        deserialize_bytecode(b"QY\x00\x01\x00\x00")


def test_pretty_print_options():
    """Test pretty print with different options."""
    func = BytecodeFunction(
        name=Symbol("test"),
        params=(),
        register_count=1,
        instructions=(Instruction("RETURN", (0,)),),
    )
    program = BytecodeProgram(functions=(func,))

    # Without spans
    output1 = pretty_print_bytecode(program, show_spans=False)
    assert "@" not in output1

    # Without diagnostics
    output2 = pretty_print_bytecode(program, show_diagnostics=False)
    assert "Diagnostics:" not in output2

    # Custom indent
    output3 = pretty_print_bytecode(program, indent="    ")
    assert "    Registers:" in output3


def test_empty_program():
    """Test handling of empty program."""
    program = BytecodeProgram(functions=())
    dump = dump_bytecode(program)
    assert dump == ""

    pretty = pretty_print_bytecode(program)
    assert "Bytecode Program" in pretty


def test_complex_operands():
    """Test serialization of complex operands."""
    func = BytecodeFunction(
        name=Symbol("test"),
        params=(),
        register_count=3,
        instructions=(
            Instruction("BUILD_TUPLE", (0, 1, 2, 3)),
            Instruction("LOAD_HOST", (1, (1, 2, 3))),
            Instruction("LOAD_HOST", (2, {"key": "value"})),
            Instruction("RETURN", (0,)),
        ),
    )
    program = BytecodeProgram(functions=(func,))

    data = serialize_bytecode(program)
    restored = deserialize_bytecode(data)

    assert len(restored.functions[0].instructions) == 4
    assert restored.functions[0].instructions[1].operands[1] == (1, 2, 3)
    assert restored.functions[0].instructions[2].operands[1] == {"key": "value"}
