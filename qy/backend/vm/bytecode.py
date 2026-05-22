# coding: utf-8
"""Bytecode 平台无关定义。.

目标：
- 定义 bytecode program/function/instruction 的完整数据结构
- 提供 dump、pretty print、binary serialization
- 替代 qy/bytecode.py 中的规格部分

当前：
- 从 qy/bytecode.py 迁移核心数据结构
- 添加 diagnostics 支持
- 提供完整的 dump 和 pretty print

禁止：
- 不得包含 runtime value（如 BytecodeFunctionValue，那属于 qy/vm/）
- 不得包含具体的执行逻辑
- 不得依赖某个 Python VM instance
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import TYPE_CHECKING
from typing import Literal

from qy.diag import Diagnostic

if TYPE_CHECKING:
    from qy.errors import SourceSpan
    from qy.frontend.reader import Symbol

__all__ = [
    "BytecodeFunction",
    "BytecodeProgram",
    "Instruction",
    "Opcode",
    "Register",
    "deserialize_bytecode",
    "dump_bytecode",
    "pretty_print_bytecode",
    "serialize_bytecode",
]

Register = int

Opcode = Literal[
    "APPEND_RESULT",
    "ALL_GATHER",
    "APPLY",
    "BUILD_TUPLE",
    "CACHE_EVAL",
    "CALL",
    "DEFEFFECT",
    "DEFINE_MODULE",
    "DEFINE_ONCE",
    "ENTER_SCOPE",
    "EXIT_SCOPE",
    "FROM_IMPORT",
    "HANDLE",
    "JUMP",
    "JUMP_IF_FALSE",
    "LOAD_HOST",
    "LOAD_ENV",
    "MAKE_MACRO",
    "MAKE_FUNCTION",
    "MOVE",
    "PARALLEL_GATHER",
    "PERFORM",
    "RAISE_EFFECT",
    "RACE_FIRST",
    "RESUME",
    "RETURN",
    "RUNTIME_EVAL",
    "STORE_LOCAL",
    "TAIL_CALL",
]


@dataclass(frozen=True, slots=True)
class Instruction:
    """单条 bytecode 指令。.

    Attributes:
        opcode: 操作码
        operands: 操作数元组，可以是 Register、Symbol、literal value、label 等
        span: 源码位置信息（可选）
    """

    opcode: Opcode
    operands: tuple[object, ...] = ()
    span: SourceSpan | None = None


@dataclass(frozen=True, slots=True)
class BytecodeFunction:
    """Bytecode 函数。.

    Attributes:
        name: 函数名（Symbol）
        params: 参数名列表（Symbol）
        register_count: 寄存器数量
        instructions: 指令序列
    """

    name: Symbol
    params: tuple[Symbol, ...]
    register_count: int
    instructions: tuple[Instruction, ...]


@dataclass(frozen=True, slots=True)
class BytecodeProgram:
    """Bytecode 程序。.

    Attributes:
        functions: 函数列表
        main: 主函数索引（默认为 0）
        diagnostics: 诊断信息
    """

    functions: tuple[BytecodeFunction, ...]
    main: int = 0
    diagnostics: tuple[Diagnostic, ...] = ()

    @property
    def ok(self) -> bool:
        """检查程序是否没有错误。."""
        return not any(diagnostic.severity == "error" for diagnostic in self.diagnostics)


def dump_bytecode(program: BytecodeProgram) -> str:
    """Dump bytecode program to text format (compact).

    Args:
        program: BytecodeProgram to dump

    Returns:
        Text representation of the program
    """
    lines: list[str] = []
    for index, function in enumerate(program.functions):
        params = ", ".join(param.name for param in function.params)
        suffix = " [main]" if index == program.main else ""
        lines.append(
            f"fn#{index} {function.name.name}({params}) regs={function.register_count}{suffix}"
        )
        if not function.instructions:
            lines.append("  ; no instructions")
            continue
        for instruction_index, instruction in enumerate(function.instructions):
            lines.append(
                f"  {instruction_index:04d}: {_format_instruction(instruction)}{_format_span(instruction.span)}"
            )
    if program.diagnostics:
        lines.append("diagnostics:")
        lines.extend(
            f"  - {diagnostic.severity}: {diagnostic.message}" for diagnostic in program.diagnostics
        )
    return "\n".join(lines)


def pretty_print_bytecode(
    program: BytecodeProgram,
    *,
    show_spans: bool = True,
    show_diagnostics: bool = True,
    indent: str = "  ",
) -> str:
    """Pretty print bytecode program with formatting options.

    Args:
        program: BytecodeProgram to print
        show_spans: Whether to show source spans
        show_diagnostics: Whether to show diagnostics
        indent: Indentation string

    Returns:
        Pretty-printed text representation
    """
    lines: list[str] = []
    lines.append("=" * 60)
    lines.append(f"Bytecode Program (main=fn#{program.main})")
    lines.append("=" * 60)

    for index, function in enumerate(program.functions):
        lines.append("")
        params = ", ".join(param.name for param in function.params)
        is_main = " [MAIN]" if index == program.main else ""
        lines.append(f"Function #{index}: {function.name.name}({params}){is_main}")
        lines.append(f"{indent}Registers: {function.register_count}")
        lines.append(f"{indent}Instructions: {len(function.instructions)}")

        if not function.instructions:
            lines.append(f"{indent}; (empty)")
            continue

        lines.append("")
        for inst_idx, instruction in enumerate(function.instructions):
            inst_str = _format_instruction(instruction)
            span_str = _format_span(instruction.span) if show_spans else ""
            lines.append(f"{indent}{inst_idx:04d}: {inst_str}{span_str}")

    if show_diagnostics and program.diagnostics:
        lines.append("")
        lines.append("=" * 60)
        lines.append("Diagnostics:")
        lines.append("=" * 60)
        for diagnostic in program.diagnostics:
            lines.append(f"{indent}[{diagnostic.severity.upper()}] {diagnostic.message}")

    lines.append("")
    return "\n".join(lines)


def serialize_bytecode(program: BytecodeProgram) -> bytes:
    r"""Serialize bytecode program to binary format.

    Binary format:
        Header:
            - Magic: b'QY\\x00\\x01' (4 bytes)
            - Version: uint16 (2 bytes)
            - Main index: uint32 (4 bytes)
            - Function count: uint32 (4 bytes)
            - Diagnostic count: uint32 (4 bytes)

        For each function:
            - Name length: uint32 (4 bytes)
            - Name: UTF-8 string
            - Param count: uint32 (4 bytes)
            - For each param:
                - Param name length: uint32 (4 bytes)
                - Param name: UTF-8 string
            - Register count: uint32 (4 bytes)
            - Instruction count: uint32 (4 bytes)
            - For each instruction:
                - Opcode length: uint32 (4 bytes)
                - Opcode: UTF-8 string
                - Operand count: uint32 (4 bytes)
                - For each operand: pickled object

        For each diagnostic:
            - Severity length: uint32 (4 bytes)
            - Severity: UTF-8 string
            - Message length: uint32 (4 bytes)
            - Message: UTF-8 string

    Args:
        program: BytecodeProgram to serialize

    Returns:
        Binary representation
    """
    import pickle

    parts: list[bytes] = []

    # Header
    parts.append(b"QY\x00\x01")  # Magic
    parts.append(struct.pack("<H", 1))  # Version
    parts.append(struct.pack("<I", program.main))
    parts.append(struct.pack("<I", len(program.functions)))
    parts.append(struct.pack("<I", len(program.diagnostics)))

    # Functions
    for function in program.functions:
        name_bytes = function.name.name.encode("utf-8")
        parts.append(struct.pack("<I", len(name_bytes)))
        parts.append(name_bytes)

        parts.append(struct.pack("<I", len(function.params)))
        for param in function.params:
            param_bytes = param.name.encode("utf-8")
            parts.append(struct.pack("<I", len(param_bytes)))
            parts.append(param_bytes)

        parts.append(struct.pack("<I", function.register_count))
        parts.append(struct.pack("<I", len(function.instructions)))

        for instruction in function.instructions:
            opcode_bytes = instruction.opcode.encode("utf-8")
            parts.append(struct.pack("<I", len(opcode_bytes)))
            parts.append(opcode_bytes)

            parts.append(struct.pack("<I", len(instruction.operands)))
            for operand in instruction.operands:
                operand_bytes = pickle.dumps(operand)
                parts.append(struct.pack("<I", len(operand_bytes)))
                parts.append(operand_bytes)

    # Diagnostics
    for diagnostic in program.diagnostics:
        severity_bytes = diagnostic.severity.encode("utf-8")
        parts.append(struct.pack("<I", len(severity_bytes)))
        parts.append(severity_bytes)

        message_bytes = diagnostic.message.encode("utf-8")
        parts.append(struct.pack("<I", len(message_bytes)))
        parts.append(message_bytes)

    return b"".join(parts)


def deserialize_bytecode(data: bytes) -> BytecodeProgram:
    """Deserialize bytecode program from binary format.

    Args:
        data: Binary data

    Returns:
        Deserialized BytecodeProgram

    Raises:
        ValueError: If data is invalid
    """
    import pickle

    from qy.frontend.reader import Symbol

    offset = 0

    def read_bytes(n: int) -> bytes:
        nonlocal offset
        result = data[offset : offset + n]
        if len(result) != n:
            raise ValueError(f"Unexpected end of data at offset {offset}")
        offset += n
        return result

    def read_uint32() -> int:
        return struct.unpack("<I", read_bytes(4))[0]

    def read_uint16() -> int:
        return struct.unpack("<H", read_bytes(2))[0]

    def read_string() -> str:
        length = read_uint32()
        return read_bytes(length).decode("utf-8")

    # Header
    magic = read_bytes(4)
    if magic != b"QY\x00\x01":
        raise ValueError(f"Invalid magic: {magic!r}")

    version = read_uint16()
    if version != 1:
        raise ValueError(f"Unsupported version: {version}")

    main_index = read_uint32()
    function_count = read_uint32()
    diagnostic_count = read_uint32()

    # Functions
    functions: list[BytecodeFunction] = []
    for _ in range(function_count):
        name = Symbol(read_string())

        param_count = read_uint32()
        params = tuple(Symbol(read_string()) for _ in range(param_count))

        register_count = read_uint32()
        instruction_count = read_uint32()

        instructions: list[Instruction] = []
        for _ in range(instruction_count):
            opcode = read_string()
            operand_count = read_uint32()

            operands: list[object] = []
            for _ in range(operand_count):
                operand_length = read_uint32()
                operand_bytes = read_bytes(operand_length)
                operands.append(pickle.loads(operand_bytes))

            instructions.append(Instruction(opcode, tuple(operands), None))  # type: ignore

        functions.append(BytecodeFunction(name, params, register_count, tuple(instructions)))

    # Diagnostics
    diagnostics: list[Diagnostic] = []
    for _ in range(diagnostic_count):
        severity = read_string()
        message = read_string()
        diagnostics.append(Diagnostic(message, severity=severity))  # type: ignore

    return BytecodeProgram(tuple(functions), main_index, tuple(diagnostics))


def _format_instruction(instruction: Instruction) -> str:
    """Format instruction for display."""
    if not instruction.operands:
        return instruction.opcode
    return (
        f"{instruction.opcode} {', '.join(_format_operand(item) for item in instruction.operands)}"
    )


def _format_operand(value: object) -> str:
    """Format operand for display."""
    from qy.frontend.reader import Symbol

    if isinstance(value, Symbol):
        return value.name
    if isinstance(value, tuple):
        return f"({', '.join(_format_operand(item) for item in value)})"
    return repr(value)


def _format_span(span: SourceSpan | None) -> str:
    """Format source span for display."""
    if span is None:
        return ""
    return f" @ {span.format()}"
