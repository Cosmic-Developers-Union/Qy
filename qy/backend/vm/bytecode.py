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
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING
from typing import cast

from qy.backend.vm.spec.opcode import Opcode as SpecOpcode
from qy.diag import Diagnostic

if TYPE_CHECKING:
    from qy.core.syntax import Symbol
    from qy.errors import SourceSpan
    from qy.ir.layout import SymbolSpaceLayout

__all__ = [
    "BytecodeFunction",
    "BytecodeProgram",
    "Instruction",
    "Opcode",
    "Register",
    "deserialize_bytecode",
    "dump_bytecode",
    "load_bytecode_json",
    "pretty_print_bytecode",
    "serialize_bytecode",
    "serialize_bytecode_json",
]

Register = int

# Bytecode opcode 的唯一事实源是 qy/backend/vm/spec/opcode.py（VM 稳定契约）；
# 这里只重导出，避免出现第二份 opcode 列表（历史上两份曾漂移）。
Opcode = SpecOpcode


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
    # Abstract-machine dialect only: program-level symbol-space layout used by
    # SLOT_COMPLETE to recover the bound symbol from a (space, slot) address.
    symbol_spaces: tuple[SymbolSpaceLayout, ...] = ()


@dataclass(frozen=True, slots=True)
class BytecodeProgram:
    """Bytecode 程序。.

    Attributes:
        functions: 函数列表
        main: 主函数索引（默认为 0）
        diagnostics: 诊断信息
        symbol_spaces: 从 HIR 经 MIR/LIR 下沉的程序级 symbol-space layout
            （``qy.ir.layout.SymbolSpaceLayout``）；不再在 backend 边界丢失。
    """

    functions: tuple[BytecodeFunction, ...]
    main: int = 0
    diagnostics: tuple[Diagnostic, ...] = ()
    symbol_spaces: tuple[SymbolSpaceLayout, ...] = ()

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

    from qy.core.syntax import Symbol

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
    from qy.core.syntax import Symbol
    from qy.core.syntax import TValue
    from qy.import_.parse import ImportSpec
    from qy.sem.runtime import EffectDefinition

    def encode_value(value: object) -> dict:
        if value is None or isinstance(value, QyNil):
            return {"type": "nil"}
        if isinstance(value, TValue):
            return {"type": "t"}
        from qy.core.syntax import NONE as QY_NONE
        from qy.core.syntax import NoneValue as QyNoneValue

        if isinstance(value, QyNoneValue) or value is QY_NONE:
            return {"type": "none"}
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
        semantic = _encode_semantic_value(value, encode_value)
        if semantic is not None:
            return semantic
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

    program_json: dict[str, object] = {
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


_SEMANTIC_VALUE_REGISTRY: dict[str, type] | None = None
_SEMANTIC_VALUE_BY_CLASS: dict[str, type] | None = None


def _semantic_value_tables() -> tuple[dict[str, type], dict[str, type]]:
    """按 type_name / 类名索引 qy.sem.core 的值类型（惰性构建）。."""
    global _SEMANTIC_VALUE_REGISTRY, _SEMANTIC_VALUE_BY_CLASS
    if _SEMANTIC_VALUE_REGISTRY is None or _SEMANTIC_VALUE_BY_CLASS is None:
        import dataclasses as _dataclasses

        import qy.sem.core as sem_core

        by_type: dict[str, type] = {}
        by_class: dict[str, type] = {}
        for name in dir(sem_core):
            obj = getattr(sem_core, name)
            if not isinstance(obj, type) or obj is sem_core.Value:
                continue
            if not issubclass(obj, sem_core.Value) or not _dataclasses.is_dataclass(obj):
                continue
            by_class[obj.__name__] = obj
            type_name = getattr(obj, "type_name", None)
            if isinstance(type_name, str):
                by_type.setdefault(type_name, obj)
        _SEMANTIC_VALUE_REGISTRY = by_type
        _SEMANTIC_VALUE_BY_CLASS = by_class
    return _SEMANTIC_VALUE_REGISTRY, _SEMANTIC_VALUE_BY_CLASS


def _encode_semantic_value(value: object, encode: Callable[[object], object]) -> dict | None:
    """把 Qy 语义值编码成 ``{type, class, value}``；不是语义值时返回 None。."""
    import dataclasses as _dataclasses

    from qy.sem.core import Value as QyValue

    if not isinstance(value, QyValue) or not _dataclasses.is_dataclass(value):
        return None
    type_name = getattr(value, "type_name", None)
    if not isinstance(type_name, str):
        return None
    fields = _dataclasses.fields(value)
    if not fields:
        return {"type": type_name, "class": type(value).__name__, "value": {}}
    return {
        "type": type_name,
        "class": type(value).__name__,
        "value": {field.name: encode(getattr(value, field.name)) for field in fields},
    }


def _decode_semantic_value(payload: dict, decode: Callable[[object], object]) -> object | None:
    """把 ``{type, class, value}`` 还原为 qy.sem.core 的值对象；不匹配返回 None。."""
    import dataclasses as _dataclasses

    by_type, by_class = _semantic_value_tables()
    class_name = payload.get("class")
    # 只有显式带 class 的载荷才是"语义值"；旧式裸 {"type":"string"} 保持原生标量语义
    # （例如 ArrayValue.element_type 是普通 str）。
    if not isinstance(class_name, str):
        return None
    target = by_class.get(class_name) or by_type.get(str(payload.get("type")))
    if target is None:
        return None
    raw = payload.get("value")
    data = raw if isinstance(raw, dict) else {}
    kwargs = {field.name: decode(data.get(field.name)) for field in _dataclasses.fields(target)}
    return target(**kwargs)


def load_bytecode_json(text: str) -> BytecodeProgram:
    """Load a program from the JSON interchange format produced by serialize_bytecode_json.

    这是 `qy export` 的**对端**：交换格式必须能被所有宿主 VM 读入，否则它不是契约。
    值按 Qy 语义重建（nil / T / int / float / string / symbol / chain / effect_def），
    寄存器位置还原为 int，寄存器元组还原为 tuple[int]，handler / import 规格还原为
    对应结构。
    """
    import json

    from qy.core.syntax import Chain
    from qy.core.syntax import Symbol
    from qy.core.syntax import T as QY_T
    from qy.core.syntax import nil as QY_NIL
    from qy.import_.parse import ImportSpec
    from qy.sem.runtime import EffectDefinition

    def as_int(value: object, default: int = 0) -> int:
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, (int, float, str)):
            try:
                return int(value)
            except ValueError:
                return default
        return default

    def decode_chain(value: object) -> object:
        if value is None:
            return QY_NIL
        if not isinstance(value, dict):
            return decode_value(value)
        tail = decode_chain(value.get("tail"))
        return Chain(decode_value(value.get("head")), tail)

    def decode_value(payload: object) -> object:
        if not isinstance(payload, dict):
            return payload
        kind = payload.get("type")
        raw = payload.get("value")
        semantic = _decode_semantic_value(payload, decode_value)
        if semantic is not None:
            return semantic
        if kind == "nil":
            return QY_NIL
        if kind == "t":
            return QY_T
        if kind == "none":
            from qy.core.syntax import NONE as QY_NONE

            return QY_NONE
        if kind in ("int", "float", "bool", "string"):
            return raw
        if kind == "symbol":
            return Symbol(str(raw))
        if kind == "chain":
            return decode_chain(raw)
        if kind == "effect_def":
            data = raw if isinstance(raw, dict) else {}
            return EffectDefinition(
                Symbol(str(data.get("name", ""))),
                resumable=bool(data.get("resumable", True)),
            )
        if kind == "list":
            return [decode_value(item) for item in raw] if isinstance(raw, list) else []
        if kind == "tuple":
            return tuple(decode_value(item) for item in raw) if isinstance(raw, list) else ()
        if kind == "reg_tuple":
            return tuple(as_int(item) for item in raw) if isinstance(raw, list) else ()
        if kind == "symbol_tuple":
            return tuple(Symbol(str(item)) for item in raw) if isinstance(raw, list) else ()
        if kind == "handler_specs":
            specs = raw if isinstance(raw, list) else []
            return tuple(
                (Symbol(str(spec.get("effect", ""))), as_int(spec.get("handler_fn"), -1))
                for spec in specs
                if isinstance(spec, dict)
            )
        if kind == "import_specs":
            specs = raw if isinstance(raw, list) else []
            return tuple(
                ImportSpec(Symbol(str(spec.get("name", ""))), Symbol(str(spec.get("alias", ""))))
                for spec in specs
                if isinstance(spec, dict)
            )
        if kind == "unknown":
            raise ValueError(
                f"bytecode JSON contains an unencodable value: {raw!r}; "
                "the interchange format must encode every constant"
            )
        return raw

    def decode_operand(payload: object) -> object:
        if not isinstance(payload, dict):
            return payload
        if payload.get("type") == "reg":
            raw = payload.get("value")
            return int(raw) if isinstance(raw, (int, float)) else raw
        return decode_value(payload)

    data = json.loads(text)
    version = data.get("version")
    if version != 1:
        raise ValueError(f"unsupported bytecode JSON version: {version!r}")
    functions: list[BytecodeFunction] = []
    for raw_function in data.get("functions", []):
        instructions = tuple(
            Instruction(
                cast(Opcode, str(raw_instruction.get("opcode", ""))),
                tuple(decode_operand(item) for item in raw_instruction.get("operands", [])),
            )
            for raw_instruction in raw_function.get("instructions", [])
        )
        functions.append(
            BytecodeFunction(
                Symbol(str(raw_function.get("name", ""))),
                tuple(Symbol(str(param)) for param in raw_function.get("params", [])),
                int(raw_function.get("register_count", 0)),
                instructions,
            )
        )
    return BytecodeProgram(tuple(functions), int(data.get("main", 0)))


def _format_instruction(instruction: Instruction) -> str:
    """Format instruction for display."""
    if not instruction.operands:
        return instruction.opcode
    return (
        f"{instruction.opcode} {', '.join(_format_operand(item) for item in instruction.operands)}"
    )


def _format_operand(value: object) -> str:
    """Format operand for display."""
    from qy.core.syntax import Symbol

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
