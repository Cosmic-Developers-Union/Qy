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
    "serialize_bytecode_json",
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


def serialize_bytecode_json(program: BytecodeProgram, *, env=None) -> str:
    """Serialize bytecode program to JSON interchange format for external VMs."""
    import json

    from qy.core.syntax import Chain
    from qy.core.syntax import QyNil
    from qy.frontend.reader import Symbol
    from qy.sem.core import TValue
    from qy.sem.runtime import EffectDefinition
    from qy.std.imports import ImportSpec

    def encode_value(value: object) -> dict:
        if value is None or isinstance(value, QyNil):
            return {"type": "nil"}
        if isinstance(value, TValue):
            return {"type": "t"}
        if isinstance(value, bool):
            return {"type": "bool", "value": value}
        if isinstance(value, int):
            return {"type": "int", "value": value}
        if isinstance(value, float):
            return {"type": "float", "value": value}
        if isinstance(value, str):
            return {"type": "string", "value": value}
        if isinstance(value, Symbol):
            return {"type": "symbol", "value": value.name}
        if isinstance(value, Chain):
            return {"type": "chain", "value": encode_chain(value)}
        if isinstance(value, EffectDefinition):
            return {
                "type": "effect_def",
                "value": {"name": value.name.name, "resumable": value.resumable},
            }
        if isinstance(value, list):
            return {"type": "list", "value": [encode_value(v) for v in value]}
        if isinstance(value, tuple):
            return {"type": "tuple", "value": [encode_value(v) for v in value]}
        return {"type": "unknown", "value": repr(value)}

    def encode_chain(chain: object) -> object:
        if chain is None or isinstance(chain, QyNil):
            return None
        if isinstance(chain, Chain):
            return {"head": encode_value(chain.head), "tail": encode_chain(chain.tail)}
        return encode_value(chain)

    def encode_operands(opcode: str, operands: tuple[object, ...]) -> list[dict]:
        result = []
        for i, operand in enumerate(operands):
            result.append(encode_operand(opcode, i, operand, operands))
        return result

    def encode_operand(opcode: str, index: int, operand: object, all_operands: tuple) -> dict:
        if isinstance(operand, Symbol):
            return {"type": "symbol", "value": operand.name}
        if isinstance(operand, tuple):
            return encode_tuple_operand(opcode, index, operand)
        if isinstance(operand, bool):
            return {"type": "bool", "value": operand}
        if isinstance(operand, int):
            if _is_register_position(opcode, index, all_operands):
                return {"type": "reg", "value": operand}
            return {"type": "int", "value": operand}
        return encode_value(operand)

    def encode_tuple_operand(opcode: str, index: int, value: tuple) -> dict:
        if opcode == "CALL" and index == 2:
            return {"type": "reg_tuple", "value": [v for v in value]}
        if opcode == "TAIL_CALL" and index == 1:
            return {"type": "reg_tuple", "value": [v for v in value]}
        if opcode == "HANDLE" and index == 2:
            specs = []
            for spec in value:
                if isinstance(spec, tuple) and len(spec) == 2:
                    effect_sym, handler_fn_idx = spec
                    specs.append(
                        {
                            "effect": effect_sym.name
                            if isinstance(effect_sym, Symbol)
                            else str(effect_sym),
                            "handler_fn": handler_fn_idx,
                        }
                    )
            return {"type": "handler_specs", "value": specs}
        if opcode == "FROM_IMPORT" and index == 1:
            specs = []
            for spec in value:
                if isinstance(spec, ImportSpec):
                    specs.append({"name": spec.name.name, "alias": spec.alias.name})
                elif isinstance(spec, tuple) and len(spec) == 2:
                    specs.append(
                        {
                            "name": spec[0].name if isinstance(spec[0], Symbol) else str(spec[0]),
                            "alias": spec[1].name if isinstance(spec[1], Symbol) else str(spec[1]),
                        }
                    )
            return {"type": "import_specs", "value": specs}
        if opcode == "DEFINE_MODULE" and index == 3:
            return {
                "type": "symbol_tuple",
                "value": [s.name if isinstance(s, Symbol) else str(s) for s in value],
            }
        return {"type": "tuple", "value": [encode_value(v) for v in value]}

    def _is_register_position(opcode: str, index: int, all_operands: tuple) -> bool:
        from qy.backend.vm.spec.opcode import OPCODE_TABLE

        info = OPCODE_TABLE.get(opcode)
        if info is None:
            return False
        if info.has_dest and index == 0:
            return True
        if opcode == "MOVE":
            return True
        if opcode == "STORE_LOCAL" and index == 1:
            return True
        if opcode == "DEFINE_ONCE" and index == 1:
            return True
        if opcode == "APPEND_RESULT" and index == 0:
            return True
        if opcode == "RETURN" and index == 0:
            return True
        if opcode == "JUMP_IF_FALSE" and index == 0:
            return True
        if opcode == "PERFORM" and index == 2:
            return True
        if opcode == "RESUME" and index in (1, 2):
            return True
        if opcode == "RAISE_EFFECT" and index == 1:
            return True
        if opcode == "APPLY" and index in (1, 2):
            return True
        if opcode == "BUILD_TUPLE" and index > 0:
            return True
        if opcode == "CALL" and index == 1:
            return True
        if opcode == "TAIL_CALL" and index == 0:
            return True
        if opcode in ("PARALLEL_GATHER", "ALL_GATHER", "RACE_FIRST") and index > 0:
            return True
        if opcode == "CACHE_EVAL" and index == 1:
            return True
        if opcode == "RUNTIME_EVAL" and index == 1:
            return True
        if opcode == "LOAD_ENV" and index == 1:
            return False
        if opcode == "HANDLE" and index == 1:
            return False
        return False

    functions_json = []
    for func in program.functions:
        instructions_json = []
        for instr in func.instructions:
            instructions_json.append(
                {
                    "opcode": instr.opcode,
                    "operands": encode_operands(instr.opcode, instr.operands),
                }
            )
        functions_json.append(
            {
                "name": func.name.name,
                "params": [p.name for p in func.params],
                "register_count": func.register_count,
                "instructions": instructions_json,
            }
        )

    program_json = {
        "version": 1,
        "main": program.main,
        "functions": functions_json,
    }

    if env is not None:
        hygiene_bindings = {}
        for func in program.functions:
            for instr in func.instructions:
                for op in instr.operands:
                    if isinstance(op, Symbol) and "__qy_hygiene" in op.name:
                        if op.name not in hygiene_bindings:
                            try:
                                val = env.resolve(op)
                                base_name = getattr(val, "name", None)
                                if base_name:
                                    hygiene_bindings[op.name] = base_name
                            except Exception:
                                pass
        if hygiene_bindings:
            program_json["hygiene_bindings"] = hygiene_bindings

    return json.dumps(program_json, ensure_ascii=False, separators=(",", ":"))


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
