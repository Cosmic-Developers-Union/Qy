"""Mid-level IR for the bytecode pipeline.

MIR uses virtual registers instead of SSA values.
Each basic block contains zero or more instructions followed by exactly one
terminator, and tail calls are modeled as terminators so control flow remains
explicit for later bytecode lowering.
"""

# coding: utf-8

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from typing import Literal

from qy.diagnostics import Diagnostic
from qy.errors import SourceSpan
from qy.reader import Symbol

__all__ = [
    "MIRBlock",
    "MIRBlockId",
    "MIRConstantPool",
    "MIRFunction",
    "MIRInstruction",
    "MIROpcode",
    "MIRProgram",
    "MIRRegister",
    "MIRTerminator",
    "MIRTerminatorOpcode",
    "dump_mir",
    "verify_mir",
]

MIRRegister = int
MIRBlockId = int

MIROpcode = Literal[
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
    "LOAD_CONST",
    "LOAD_HOST",
    "LOAD_ENV",
    "MAKE_FUNCTION",
    "MAKE_MACRO",
    "MOVE",
    "PARALLEL_GATHER",
    "PERFORM",
    "RACE_FIRST",
    "RESUME",
    "RUNTIME_EVAL",
    "STORE_LOCAL",
]

MIRTerminatorOpcode = Literal["BRANCH", "JUMP", "RAISE_EFFECT", "RETURN", "TAIL_CALL"]


@dataclass(slots=True)
class MIRConstantPool:
    """Constant pool for MIR: stores Python objects referenced by index.

    Same value always gets the same index (interning).  This makes MIR
    serialisable and portable -- instructions reference constants by integer
    index instead of embedding Python objects directly.
    """

    _values: list[object]
    _index: dict[object, int]

    def __init__(self) -> None:
        self._values = []
        self._index = {}

    def intern(self, value: object) -> int:
        """Insert *value* into the pool and return its index.

        Each call always produces a fresh index — no deduplication.
        This preserves identity semantics for values like Symbols.
        """
        idx = len(self._values)
        self._values.append(value)
        return idx

    def get(self, index: int) -> object:
        """Return the constant at *index*."""
        return self._values[index]

    @property
    def values(self) -> tuple[object, ...]:
        return tuple(self._values)


@dataclass(frozen=True, slots=True)
class MIRInstruction:
    opcode: MIROpcode
    operands: tuple[object, ...] = ()
    span: SourceSpan | None = None


@dataclass(frozen=True, slots=True)
class MIRTerminator:
    opcode: MIRTerminatorOpcode
    operands: tuple[object, ...] = ()
    span: SourceSpan | None = None


@dataclass(frozen=True, slots=True)
class MIRBlock:
    id: MIRBlockId
    instructions: tuple[MIRInstruction, ...]
    terminator: MIRTerminator


@dataclass(frozen=True, slots=True)
class MIRFunction:
    name: Symbol
    params: tuple[Symbol, ...]
    register_count: int
    blocks: tuple[MIRBlock, ...]
    entry: MIRBlockId = 0


@dataclass(frozen=True, slots=True)
class MIRProgram:
    functions: tuple[MIRFunction, ...]
    constants: MIRConstantPool = field(default_factory=MIRConstantPool)
    main: int = 0
    diagnostics: tuple[Diagnostic, ...] = ()

    @property
    def ok(self) -> bool:
        return not any(diagnostic.severity == "error" for diagnostic in self.diagnostics)


def verify_mir(program: MIRProgram) -> tuple[Diagnostic, ...]:
    diagnostics: list[Diagnostic] = []
    if not 0 <= program.main < len(program.functions):
        diagnostics.append(
            Diagnostic(
                f"main function index {program.main} is out of range for {len(program.functions)} MIR functions"
            )
        )
    for function in program.functions:
        _verify_function(function, diagnostics)
    return tuple(diagnostics)


def dump_mir(program: MIRProgram) -> str:
    sections: list[str] = []
    if program.constants.values:
        constant_lines = ["constant pool:"]
        for idx, value in enumerate(program.constants.values):
            constant_lines.append(f"  #{idx}: {value!r}")
        sections.append("\n".join(constant_lines))
    sections.extend(
        _dump_mir_function(index, function, is_main=index == program.main)
        for index, function in enumerate(program.functions)
    )
    if program.diagnostics:
        diagnostics = ["diagnostics:"]
        diagnostics.extend(
            f"  - {diagnostic.severity}: {diagnostic.message}" for diagnostic in program.diagnostics
        )
        sections.append("\n".join(diagnostics))
    return "\n\n".join(sections)


def _verify_function(function: MIRFunction, diagnostics: list[Diagnostic]) -> None:
    if function.register_count < 0:
        diagnostics.append(
            Diagnostic(f"function {function.name.name!r} has negative register_count")
        )
        return

    block_ids: set[MIRBlockId] = set()
    for block in function.blocks:
        if block.id in block_ids:
            diagnostics.append(
                Diagnostic(f"function {function.name.name!r} defines duplicate block bb{block.id}")
            )
            continue
        block_ids.add(block.id)

    if function.entry not in block_ids:
        diagnostics.append(
            Diagnostic(
                f"function {function.name.name!r} entry block bb{function.entry} does not exist"
            )
        )

    for block in function.blocks:
        if block.terminator is None:
            diagnostics.append(
                Diagnostic(
                    f"function {function.name.name!r} block bb{block.id} is missing a terminator"
                )
            )
            continue

        for instruction in block.instructions:
            _verify_instruction(function, block.id, instruction, diagnostics)

        _verify_terminator(function, block.id, block_ids, block.terminator, diagnostics)


def _verify_instruction(
    function: MIRFunction,
    block_id: MIRBlockId,
    instruction: MIRInstruction,
    diagnostics: list[Diagnostic],
) -> None:
    operands = instruction.operands
    if instruction.opcode == "TAIL_CALL":
        diagnostics.append(
            Diagnostic(
                f"function {function.name.name!r} block bb{block_id} uses TAIL_CALL as a non-terminator instruction"
            )
        )
        if not _check_operand_arity(
            function, block_id, "instruction", "TAIL_CALL", operands, 2, diagnostics
        ):
            return
        _check_register(function, block_id, operands[0], diagnostics)
        _check_register_tuple(function, block_id, "TAIL_CALL", operands[1], diagnostics)
        return

    match instruction.opcode:
        case "APPEND_RESULT":
            if _check_operand_arity(
                function, block_id, "instruction", instruction.opcode, operands, 1, diagnostics
            ):
                _check_register(function, block_id, operands[0], diagnostics)
        case "ALL_GATHER" | "PARALLEL_GATHER" | "RACE_FIRST":
            if len(operands) < 1:
                diagnostics.append(
                    Diagnostic(
                        f"function {function.name.name!r} block bb{block_id} instruction {instruction.opcode!r} expects at least 1 operand"
                    )
                )
            else:
                _check_register(function, block_id, operands[0], diagnostics)
        case "CACHE_EVAL":
            if not _check_operand_arity(
                function, block_id, "instruction", instruction.opcode, operands, 3, diagnostics
            ):
                return
            _check_register(function, block_id, operands[0], diagnostics)
        case "BUILD_TUPLE":
            if len(operands) < 1:
                diagnostics.append(
                    Diagnostic(
                        f"function {function.name.name!r} block bb{block_id} instruction BUILD_TUPLE expects at least 1 operand"
                    )
                )
            else:
                _check_register(function, block_id, operands[0], diagnostics)
                for reg in operands[1:]:
                    _check_register(function, block_id, reg, diagnostics)
        case "APPLY":
            if _check_operand_arity(
                function, block_id, "instruction", instruction.opcode, operands, 3, diagnostics
            ):
                _check_register(function, block_id, operands[0], diagnostics)
                _check_register(function, block_id, operands[1], diagnostics)
                _check_register(function, block_id, operands[2], diagnostics)
        case "CALL":
            if not _check_operand_arity(
                function, block_id, "instruction", instruction.opcode, operands, 3, diagnostics
            ):
                return
            _check_register(function, block_id, operands[0], diagnostics)
            _check_register(function, block_id, operands[1], diagnostics)
            _check_register_tuple(function, block_id, instruction.opcode, operands[2], diagnostics)
        case "DEFINE_MODULE":
            if not _check_operand_arity(
                function, block_id, "instruction", instruction.opcode, operands, 4, diagnostics
            ):
                return
            _check_register(function, block_id, operands[0], diagnostics)
            _check_symbol_operand(function, block_id, instruction.opcode, operands[1], diagnostics)
            _check_int_operand(function, block_id, instruction.opcode, operands[2], diagnostics)
        case "DEFEFFECT":
            if not _check_operand_arity(
                function, block_id, "instruction", instruction.opcode, operands, 2, diagnostics
            ):
                return
            _check_symbol_operand(function, block_id, instruction.opcode, operands[0], diagnostics)
            if not isinstance(operands[1], bool):
                diagnostics.append(
                    Diagnostic(
                        f"function {function.name.name!r} block bb{block_id} instruction {instruction.opcode!r} expects bool resumable operand, got {operands[1]!r}"
                    )
                )
        case "PERFORM":
            if not _check_operand_arity(
                function, block_id, "instruction", instruction.opcode, operands, 3, diagnostics
            ):
                return
            _check_register(function, block_id, operands[0], diagnostics)
            _check_symbol_operand(function, block_id, instruction.opcode, operands[1], diagnostics)
            _check_register(function, block_id, operands[2], diagnostics)
        case "HANDLE":
            if not _check_operand_arity(
                function, block_id, "instruction", instruction.opcode, operands, 3, diagnostics
            ):
                return
            _check_register(function, block_id, operands[0], diagnostics)
            _check_int_operand(function, block_id, instruction.opcode, operands[1], diagnostics)
            _check_tuple_operand(
                function,
                block_id,
                instruction.opcode,
                "handler specs tuple",
                operands[2],
                diagnostics,
            )
        case "RESUME":
            if not _check_operand_arity(
                function, block_id, "instruction", instruction.opcode, operands, 3, diagnostics
            ):
                return
            _check_register(function, block_id, operands[0], diagnostics)
            _check_register(function, block_id, operands[1], diagnostics)
            _check_register(function, block_id, operands[2], diagnostics)
        case "FROM_IMPORT":
            if not _check_operand_arity(
                function, block_id, "instruction", instruction.opcode, operands, 2, diagnostics
            ):
                return
            _check_symbol_operand(function, block_id, instruction.opcode, operands[0], diagnostics)
            _check_tuple_operand(
                function,
                block_id,
                instruction.opcode,
                "import specs tuple",
                operands[1],
                diagnostics,
            )
        case "LOAD_HOST":
            if _check_operand_arity(
                function, block_id, "instruction", instruction.opcode, operands, 2, diagnostics
            ):
                _check_register(function, block_id, operands[0], diagnostics)
        case "LOAD_CONST":
            if _check_operand_arity(
                function, block_id, "instruction", instruction.opcode, operands, 2, diagnostics
            ):
                _check_register(function, block_id, operands[0], diagnostics)
                _check_int_operand(function, block_id, instruction.opcode, operands[1], diagnostics)
        case "LOAD_ENV":
            if not _check_operand_arity(
                function, block_id, "instruction", instruction.opcode, operands, 2, diagnostics
            ):
                return
            _check_register(function, block_id, operands[0], diagnostics)
            _check_symbol_operand(function, block_id, instruction.opcode, operands[1], diagnostics)
        case "MAKE_FUNCTION":
            if not _check_operand_arity(
                function, block_id, "instruction", instruction.opcode, operands, 2, diagnostics
            ):
                return
            _check_register(function, block_id, operands[0], diagnostics)
            _check_int_operand(function, block_id, instruction.opcode, operands[1], diagnostics)
        case "MAKE_MACRO":
            if not _check_operand_arity(
                function, block_id, "instruction", instruction.opcode, operands, 4, diagnostics
            ):
                return
            _check_register(function, block_id, operands[0], diagnostics)
            _check_symbol_operand(function, block_id, instruction.opcode, operands[1], diagnostics)
            _check_tuple_operand(
                function,
                block_id,
                instruction.opcode,
                "parameter tuple",
                operands[2],
                diagnostics,
            )
            _check_tuple_operand(
                function,
                block_id,
                instruction.opcode,
                "raw body tuple",
                operands[3],
                diagnostics,
            )
        case "MOVE":
            if not _check_operand_arity(
                function, block_id, "instruction", instruction.opcode, operands, 2, diagnostics
            ):
                return
            _check_register(function, block_id, operands[0], diagnostics)
            _check_register(function, block_id, operands[1], diagnostics)
        case "RUNTIME_EVAL":
            if not _check_operand_arity(
                function, block_id, "instruction", instruction.opcode, operands, 2, diagnostics
            ):
                return
            _check_register(function, block_id, operands[0], diagnostics)
            _check_register(function, block_id, operands[1], diagnostics)
        case "STORE_LOCAL" | "DEFINE_ONCE":
            if not _check_operand_arity(
                function, block_id, "instruction", instruction.opcode, operands, 2, diagnostics
            ):
                return
            _check_symbol_operand(function, block_id, instruction.opcode, operands[0], diagnostics)
            _check_register(function, block_id, operands[1], diagnostics)
        case "ENTER_SCOPE" | "EXIT_SCOPE":
            _check_operand_arity(
                function, block_id, "instruction", instruction.opcode, operands, 0, diagnostics
            )
        case _:
            diagnostics.append(
                Diagnostic(
                    f"function {function.name.name!r} block bb{block_id} uses unknown instruction opcode {instruction.opcode!r}"
                )
            )


def _verify_terminator(
    function: MIRFunction,
    block_id: MIRBlockId,
    block_ids: set[MIRBlockId],
    terminator: MIRTerminator,
    diagnostics: list[Diagnostic],
) -> None:
    operands = terminator.operands
    match terminator.opcode:
        case "JUMP":
            if not _check_operand_arity(
                function, block_id, "terminator", terminator.opcode, operands, 1, diagnostics
            ):
                return
            _check_block_target(function, block_id, operands[0], block_ids, diagnostics)
        case "BRANCH":
            if not _check_operand_arity(
                function, block_id, "terminator", terminator.opcode, operands, 3, diagnostics
            ):
                return
            _check_register(function, block_id, operands[0], diagnostics)
            _check_block_target(function, block_id, operands[1], block_ids, diagnostics)
            _check_block_target(function, block_id, operands[2], block_ids, diagnostics)
        case "RETURN":
            if not _check_operand_arity(
                function, block_id, "terminator", terminator.opcode, operands, 1, diagnostics
            ):
                return
            if operands[0] is not None:
                _check_register(function, block_id, operands[0], diagnostics)
        case "RAISE_EFFECT":
            if not _check_operand_arity(
                function, block_id, "terminator", terminator.opcode, operands, 3, diagnostics
            ):
                return
            _check_symbol_operand(function, block_id, terminator.opcode, operands[0], diagnostics)
            _check_register(function, block_id, operands[1], diagnostics)
            if not isinstance(operands[2], bool):
                diagnostics.append(
                    Diagnostic(
                        f"function {function.name.name!r} block bb{block_id} terminator {terminator.opcode!r} expects bool resumable operand, got {operands[2]!r}"
                    )
                )
        case "TAIL_CALL":
            if not _check_operand_arity(
                function, block_id, "terminator", terminator.opcode, operands, 2, diagnostics
            ):
                return
            _check_register(function, block_id, operands[0], diagnostics)
            _check_register_tuple(function, block_id, terminator.opcode, operands[1], diagnostics)
        case _:
            diagnostics.append(
                Diagnostic(
                    f"function {function.name.name!r} block bb{block_id} uses unknown terminator opcode {terminator.opcode!r}"
                )
            )


def _check_operand_arity(
    function: MIRFunction,
    block_id: MIRBlockId,
    kind: str,
    opcode: object,
    operands: tuple[object, ...],
    expected: int,
    diagnostics: list[Diagnostic],
) -> bool:
    if len(operands) == expected:
        return True
    diagnostics.append(
        Diagnostic(
            f"function {function.name.name!r} block bb{block_id} {kind} {opcode!r} expects {expected} operands, got {len(operands)}"
        )
    )
    return False


def _check_symbol_operand(
    function: MIRFunction,
    block_id: MIRBlockId,
    opcode: object,
    value: object,
    diagnostics: list[Diagnostic],
) -> None:
    if isinstance(value, Symbol):
        return
    diagnostics.append(
        Diagnostic(
            f"function {function.name.name!r} block bb{block_id} instruction {opcode!r} expects a symbol operand, got {value!r}"
        )
    )


def _check_int_operand(
    function: MIRFunction,
    block_id: MIRBlockId,
    opcode: object,
    value: object,
    diagnostics: list[Diagnostic],
) -> None:
    if isinstance(value, int):
        return
    diagnostics.append(
        Diagnostic(
            f"function {function.name.name!r} block bb{block_id} instruction {opcode!r} expects an integer operand, got {value!r}"
        )
    )


def _check_tuple_operand(
    function: MIRFunction,
    block_id: MIRBlockId,
    opcode: object,
    label: str,
    value: object,
    diagnostics: list[Diagnostic],
) -> bool:
    if isinstance(value, tuple):
        return True
    diagnostics.append(
        Diagnostic(
            f"function {function.name.name!r} block bb{block_id} instruction {opcode!r} expects {label}, got {value!r}"
        )
    )
    return False


def _check_register_tuple(
    function: MIRFunction,
    block_id: MIRBlockId,
    opcode: object,
    value: object,
    diagnostics: list[Diagnostic],
) -> None:
    if not _check_tuple_operand(
        function,
        block_id,
        opcode,
        "a register tuple",
        value,
        diagnostics,
    ):
        return
    assert isinstance(value, tuple)
    for register in value:
        _check_register(function, block_id, register, diagnostics)


def _check_block_target(
    function: MIRFunction,
    block_id: MIRBlockId,
    target: object,
    block_ids: set[MIRBlockId],
    diagnostics: list[Diagnostic],
) -> None:
    if not isinstance(target, int):
        diagnostics.append(
            Diagnostic(
                f"function {function.name.name!r} block bb{block_id} jumps to non-block target {target!r}"
            )
        )
        return
    if target not in block_ids:
        diagnostics.append(
            Diagnostic(
                f"function {function.name.name!r} block bb{block_id} jumps to missing block bb{target}"
            )
        )


def _check_register(
    function: MIRFunction,
    block_id: MIRBlockId,
    value: object,
    diagnostics: list[Diagnostic],
) -> None:
    if not isinstance(value, int):
        diagnostics.append(
            Diagnostic(
                f"function {function.name.name!r} block bb{block_id} references non-register operand {value!r} where a register is required"
            )
        )
        return
    if not 0 <= value < function.register_count:
        diagnostics.append(
            Diagnostic(
                f"function {function.name.name!r} block bb{block_id} references out-of-range register r{value} with register_count={function.register_count}"
            )
        )


def _dump_mir_function(index: int, function: MIRFunction, *, is_main: bool) -> str:
    params = ", ".join(param.name for param in function.params)
    suffix = " [main]" if is_main else ""
    lines = [
        f"fn#{index} {function.name.name}({params}) entry=bb{function.entry} regs={function.register_count}{suffix}"
    ]
    for block in function.blocks:
        lines.append(f"  bb{block.id}:")
        if not block.instructions:
            lines.append("    ; no instructions")
        else:
            lines.extend(
                f"    {_format_instruction(instruction)}" for instruction in block.instructions
            )
        lines.append(f"    {_format_terminator(block.terminator)}")
    return "\n".join(lines)


def _format_instruction(instruction: MIRInstruction) -> str:
    operands = instruction.operands
    match instruction.opcode:
        case "APPEND_RESULT":
            rendered = f"APPEND_RESULT {_format_register(operands[0])}"
        case "ALL_GATHER" | "PARALLEL_GATHER" | "RACE_FIRST":
            indices_str = " ".join(f"fn#{i}" for i in operands[1:])
            rendered = f"{_format_register(operands[0])} = {instruction.opcode} [{indices_str}]"
        case "CACHE_EVAL":
            rendered = (
                f"{_format_register(operands[0])} = CACHE_EVAL {operands[1]!r} fn#{operands[2]}"
            )
        case "BUILD_TUPLE":
            args_str = " ".join(_format_register(r) for r in operands[1:])
            rendered = f"{_format_register(operands[0])} = BUILD_TUPLE {args_str}"
        case "APPLY":
            rendered = f"{_format_register(operands[0])} = APPLY {_format_register(operands[1])} {_format_register(operands[2])}"
        case "CALL":
            rendered = (
                f"{_format_register(operands[0])} = CALL {_format_register(operands[1])} "
                f"{_format_operand(operands[2])}"
            )
        case "DEFINE_MODULE":
            rendered = f"{_format_register(operands[0])} = DEFINE_MODULE {_format_operand(operands[1])} fn#{operands[2]}"
        case "ENTER_SCOPE" | "EXIT_SCOPE":
            rendered = instruction.opcode
        case "FROM_IMPORT":
            from qy.stdlib.imports import ImportSpec

            specs = operands[1]
            specs_str = ", ".join(
                f"{s.name.name} as {s.alias.name}"
                for s in (specs if isinstance(specs, tuple) else ())
                if isinstance(s, ImportSpec)
            )
            rendered = f"FROM_IMPORT {_format_operand(operands[0])} [{specs_str}]"
        case "LOAD_CONST":
            rendered = f"{_format_register(operands[0])} = LOAD_CONST #{operands[1]}"
        case "LOAD_HOST":
            rendered = f"{_format_register(operands[0])} = LOAD_HOST {_format_operand(operands[1])}"
        case "LOAD_ENV":
            rendered = f"{_format_register(operands[0])} = LOAD_ENV {_format_operand(operands[1])}"
        case "MAKE_FUNCTION":
            rendered = f"{_format_register(operands[0])} = MAKE_FUNCTION fn#{operands[1]}"
        case "MAKE_MACRO":
            rendered = (
                f"{_format_register(operands[0])} = MAKE_MACRO {_format_operand(operands[1])} "
                f"{_format_operand(operands[2])} {_format_operand(operands[3])}"
            )
        case "MOVE":
            rendered = f"{_format_register(operands[0])} = MOVE {_format_register(operands[1])}"
        case "DEFEFFECT":
            rendered = f"DEFEFFECT {_format_operand(operands[0])}, resumable={operands[1]}"
        case "PERFORM":
            rendered = f"{_format_register(operands[0])} = PERFORM {_format_operand(operands[1])} {_format_register(operands[2])}"
        case "HANDLE":
            specs = operands[2]
            specs_str = ", ".join(
                f"{s[0].name} -> fn#{s[1]}"
                for s in (specs if isinstance(specs, tuple) else ())
                if isinstance(s, tuple) and len(s) >= 2 and isinstance(s[0], Symbol)
            )
            rendered = f"{_format_register(operands[0])} = HANDLE fn#{operands[1]} [{specs_str}]"
        case "RESUME":
            rendered = f"{_format_register(operands[0])} = RESUME {_format_register(operands[1])} {_format_register(operands[2])}"
        case "RUNTIME_EVAL":
            rendered = (
                f"{_format_register(operands[0])} = RUNTIME_EVAL {_format_register(operands[1])}"
            )
        case "STORE_LOCAL" | "DEFINE_ONCE":
            rendered = f"{instruction.opcode} {_format_operand(operands[0])}, {_format_register(operands[1])}"
        case _:
            rendered = _format_generic(instruction.opcode, operands)
    return rendered + _format_span(instruction.span)


def _format_terminator(terminator: MIRTerminator) -> str:
    operands = terminator.operands
    match terminator.opcode:
        case "BRANCH":
            rendered = f"BRANCH {_format_register(operands[0])} ? bb{operands[1]} : bb{operands[2]}"
        case "JUMP":
            rendered = f"JUMP bb{operands[0]}"
        case "RETURN":
            rendered = f"RETURN {_format_operand(operands[0])}"
        case "RAISE_EFFECT":
            rendered = f"RAISE_EFFECT {_format_operand(operands[0])}, {_format_register(operands[1])}, resumable={operands[2]}"
        case "TAIL_CALL":
            rendered = f"TAIL_CALL {_format_register(operands[0])} {_format_operand(operands[1])}"
        case _:
            rendered = _format_generic(terminator.opcode, operands)
    return rendered + _format_span(terminator.span)


def _format_register(value: object) -> str:
    return f"r{value}"


def _format_operand(value: object) -> str:
    if isinstance(value, Symbol):
        return value.name
    if isinstance(value, tuple):
        return f"({', '.join(_format_operand(item) for item in value)})"
    return repr(value)


def _format_generic(opcode: str, operands: tuple[object, ...]) -> str:
    if not operands:
        return opcode
    return f"{opcode} {', '.join(_format_operand(operand) for operand in operands)}"


def _format_span(span: SourceSpan | None) -> str:
    if span is None:
        return ""
    return f" @ {span.format()}"
