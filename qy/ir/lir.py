# coding: utf-8
# QY_DELETE_AFTER_MIGRATION: target=qy/ir/lir/__init__.py + qy/ir/lir/node.py
"""LIR (Low-level IR): Qy abstract-machine IR.

LIR is the first layer where Qy's runtime machinery must be explicit.  It is
VM-facing, but it is not bytecode and it is not a textual copy of bytecode.
The final target model is an abstract machine with virtual-stack frames,
continuation frames, handler frames, symbol-space-chain transitions, binding
slot operations, and explicit lookup operations.

The current compiler still emits ``compat`` LIR for some legacy bytecode
instructions while the abstract-machine vocabulary is being introduced.  New
low-level work should model runtime mechanisms here instead of hiding them in
the bytecode compiler or register VM.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from qy.diagnostics import Diagnostic
from qy.errors import SourceSpan
from qy.reader import Symbol

__all__ = [
    "LIRBindingAddr",
    "LIRBindingSlot",
    "LIRBindingState",
    "LIRContinuationLayout",
    "LIRDialect",
    "LIRFrameKind",
    "LIRFrameLayout",
    "LIRFunction",
    "LIRHandlerLayout",
    "LIRInstruction",
    "LIRInstructionIndex",
    "LIROpcode",
    "LIRProgram",
    "LIRRegister",
    "LIRSlotIndex",
    "LIRSymbolMeta",
    "LIRSymbolSpaceId",
    "LIRSymbolSpaceLayout",
    "dump_lir",
    "verify_lir",
]

LIRRegister = int
LIRInstructionIndex = int
LIRSymbolSpaceId = int
LIRSlotIndex = int
LIRDialect = Literal["compat", "abstract-machine"]
LIRBindingState = Literal["declared", "pending", "completed", "poisoned"]
LIRFrameKind = Literal["function", "continuation", "handler", "task"]


@dataclass(frozen=True, slots=True)
class LIRBindingAddr:
    """Stable binding address inside one symbol-space layout."""

    space: LIRSymbolSpaceId
    slot: LIRSlotIndex


@dataclass(frozen=True, slots=True)
class LIRSymbolMeta:
    """Cold metadata for a symbol-space slot."""

    symbol: Symbol
    span: SourceSpan | None = None
    flags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class LIRBindingSlot:
    """One once-complete binding slot in a symbol-space layout."""

    address: LIRBindingAddr
    symbol: Symbol
    state: LIRBindingState = "declared"
    metadata_index: int | None = None


@dataclass(frozen=True, slots=True)
class LIRSymbolSpaceLayout:
    """Low-level symbol-space layout visible to LIR and later backends."""

    id: LIRSymbolSpaceId
    name: str
    parent: LIRSymbolSpaceId | None = None
    slots: tuple[LIRBindingSlot, ...] = ()
    metadata: tuple[LIRSymbolMeta, ...] = ()


@dataclass(frozen=True, slots=True)
class LIRFrameLayout:
    """Frame layout for one Qy abstract-machine frame."""

    kind: LIRFrameKind
    name: str
    register_count: int
    local_slot_count: int = 0
    ss_chain: tuple[LIRSymbolSpaceId, ...] = ()
    saved_registers: tuple[LIRRegister, ...] = ()


@dataclass(frozen=True, slots=True)
class LIRContinuationLayout:
    """Delimited continuation layout captured by effect lowering."""

    id: int
    resume_target: LIRInstructionIndex | None = None
    saved_registers: tuple[LIRRegister, ...] = ()
    saved_spaces: tuple[LIRSymbolSpaceId, ...] = ()
    multi_shot: bool = True


@dataclass(frozen=True, slots=True)
class LIRHandlerLayout:
    """Effect handler marker layout on the virtual stack."""

    id: int
    effects: tuple[Symbol, ...] = ()
    handler_target: LIRInstructionIndex | None = None
    parent_handler: int | None = None
    ss_chain: tuple[LIRSymbolSpaceId, ...] = ()


LIROpcode = Literal[
    # -- Value loading --
    "LOAD_HOST",
    "LOAD_NIL",
    "LOAD_T",
    "LOAD_ENV",
    "MOVE",
    # -- Storage --
    "STORE_LOCAL",
    "DEFINE_ONCE",
    # -- Function construction --
    "MAKE_FUNCTION",
    "MAKE_MACRO",
    # -- Scope --
    "ENTER_SCOPE",
    "EXIT_SCOPE",
    # -- Results --
    "APPEND_RESULT",
    # -- Data construction --
    "BUILD_TUPLE",
    # -- Calls --
    "CALL",
    "TAIL_CALL",
    "APPLY",
    # -- Control flow --
    "JUMP",
    "JUMP_IF_FALSE",
    "BRANCH_NIL",
    "RETURN",
    # -- Effects --
    "DEFEFFECT",
    "PERFORM",
    "HANDLE",
    "RESUME",
    "RAISE_EFFECT",
    # -- Concurrency --
    "PARALLEL_GATHER",
    "ALL_GATHER",
    "RACE_FIRST",
    "CACHE_EVAL",
    # -- Module --
    "DEFINE_MODULE",
    "FROM_IMPORT",
    # -- Meta --
    "RUNTIME_EVAL",
    # -- Abstract machine: frame / symbol-space-chain --
    "FRAME_ENTER",
    "FRAME_LEAVE",
    "SS_ENTER",
    "SS_LEAVE",
    "SS_COPY",
    "SS_RESTORE",
    "SS_LOOKUP",
    # -- Abstract machine: binding slot --
    "SLOT_READ",
    "SLOT_COMPLETE",
    "SLOT_PENDING_EFFORT",
    # -- Abstract machine: continuation / handler --
    "CONT_CAPTURE",
    "CONT_COPY",
    "CONT_RESTORE",
    "CONT_INJECT",
    "HANDLER_PUSH",
    "HANDLER_POP",
    "EFFECT_UNWIND",
    "EFFECT_DISPATCH",
]


@dataclass(frozen=True, slots=True)
class LIRInstruction:
    opcode: LIROpcode
    operands: tuple[object, ...] = ()
    span: SourceSpan | None = None


@dataclass(frozen=True, slots=True)
class LIRFunction:
    name: Symbol
    params: tuple[Symbol, ...]
    register_count: int
    instructions: tuple[LIRInstruction, ...]
    frame_layout: LIRFrameLayout | None = None
    symbol_spaces: tuple[LIRSymbolSpaceLayout, ...] = ()
    continuations: tuple[LIRContinuationLayout, ...] = ()
    handlers: tuple[LIRHandlerLayout, ...] = ()


@dataclass(frozen=True, slots=True)
class LIRProgram:
    functions: tuple[LIRFunction, ...]
    main: int = 0
    diagnostics: tuple[Diagnostic, ...] = ()
    dialect: LIRDialect = "compat"

    @property
    def ok(self) -> bool:
        return not any(diagnostic.severity == "error" for diagnostic in self.diagnostics)


_TERMINATORS = frozenset({"RETURN", "TAIL_CALL", "RAISE_EFFECT"})
_LANGUAGE_LEVEL_EFFECT_OPCODES = frozenset({"HANDLE", "PERFORM", "RESUME"})
_JUMP_OPCODES = frozenset({"JUMP", "JUMP_IF_FALSE", "BRANCH_NIL"})


def verify_lir(program: LIRProgram) -> tuple[Diagnostic, ...]:
    diagnostics: list[Diagnostic] = []
    if program.dialect not in {"compat", "abstract-machine"}:
        diagnostics.append(Diagnostic(f"unknown LIR dialect {program.dialect!r}", severity="error"))
    for func in program.functions:
        if not func.instructions and func.name.name not in ("<lambda>",):
            diagnostics.append(
                Diagnostic(f"LIR function {func.name.name} has no instructions", severity="warning")
            )
            continue

        saw_terminator = False
        for idx, inst in enumerate(func.instructions):
            if saw_terminator:
                diagnostics.append(
                    Diagnostic(
                        f"LIR function {func.name.name} has unreachable instruction "
                        f"{inst.opcode} at {idx} after terminator",
                        severity="warning",
                    )
                )
                break
            if inst.opcode in _TERMINATORS:
                saw_terminator = True

        if not saw_terminator:
            last_opcode = func.instructions[-1].opcode
            diagnostics.append(
                Diagnostic(
                    f"LIR function {func.name.name} does not end with a terminator "
                    f"(last instruction: {last_opcode})",
                    severity="error",
                )
            )

        for idx, inst in enumerate(func.instructions):
            if (
                program.dialect == "abstract-machine"
                and inst.opcode in _LANGUAGE_LEVEL_EFFECT_OPCODES
            ):
                diagnostics.append(
                    Diagnostic(
                        f"LIR function {func.name.name} retains language-level "
                        f"effect opcode {inst.opcode} at {idx}",
                        severity="error",
                    )
                )
            if inst.opcode == "LOAD_HOST" and len(inst.operands) >= 2 and inst.operands[1] is None:
                diagnostics.append(
                    Diagnostic(
                        f"LIR LOAD_HOST None at {func.name.name}:{idx} should be LOAD_NIL",
                        severity="warning",
                    )
                )
            for operand in _register_operands_of(inst.opcode, inst.operands):
                if not isinstance(operand, int):
                    continue
                if operand < 0 or operand >= func.register_count:
                    diagnostics.append(
                        Diagnostic(
                            f"LIR function {func.name.name} uses out-of-range register r{operand} "
                            f"(register_count={func.register_count})",
                            severity="error",
                        )
                    )
            if inst.opcode in _JUMP_OPCODES and len(inst.operands) >= 1:
                target = inst.operands[-1]
                if isinstance(target, int):
                    if target < 0 or target >= len(func.instructions):
                        diagnostics.append(
                            Diagnostic(
                                f"LIR function {func.name.name} has jump to out-of-range target {target}",
                                severity="error",
                            )
                        )
    return tuple(diagnostics)


def _register_operands_of(opcode: str, operands: tuple[object, ...]) -> list[object]:
    match opcode:
        case "LOAD_HOST" | "LOAD_NIL" | "LOAD_T" | "LOAD_ENV" | "RETURN" | "APPEND_RESULT":
            return [operands[0]] if operands else []
        case "SLOT_READ" | "SS_LOOKUP" | "SLOT_PENDING_EFFORT":
            return [operands[0]] if operands else []
        case "SLOT_COMPLETE":
            return [operands[1]] if len(operands) >= 2 else []
        case "MOVE":
            return list(operands) if len(operands) >= 2 else []
        case "DEFINE_ONCE":
            return [operands[1]] if len(operands) >= 2 else []
        case "MAKE_FUNCTION" | "MAKE_MACRO":
            return [operands[0]] if operands else []
        case "CALL":
            regs = [operands[0], operands[1]] if len(operands) >= 2 else []
            if len(operands) >= 3 and isinstance(operands[2], tuple):
                regs.extend(operands[2])
            return regs
        case "TAIL_CALL":
            regs = [operands[0]] if operands else []
            if len(operands) >= 2 and isinstance(operands[1], tuple):
                regs.extend(operands[1])
            return regs
        case "BUILD_TUPLE":
            return list(operands)
        case "APPLY" | "RUNTIME_EVAL" | "RESUME":
            return list(operands)
        case "JUMP_IF_FALSE":
            return [operands[0]] if operands else []
        case "PERFORM":
            return (
                [operands[0], operands[2]]
                if len(operands) >= 3
                else [operands[0]]
                if operands
                else []
            )
        case "HANDLE":
            return [operands[0]] if operands else []
        case "RAISE_EFFECT":
            return [operands[1]] if len(operands) >= 2 else []
        case "CONT_CAPTURE":
            regs = [operands[0]] if operands else []
            if len(operands) >= 4 and isinstance(operands[3], tuple):
                regs.extend(operands[3])
            return regs
        case "CONT_COPY":
            return [operands[0], operands[1]] if len(operands) >= 2 else list(operands)
        case "CONT_RESTORE":
            return [operands[0]] if operands else []
        case "CONT_INJECT":
            return [operands[0], operands[1]] if len(operands) >= 2 else list(operands)
        case "EFFECT_UNWIND" | "EFFECT_DISPATCH":
            return list(operands)
        case "CACHE_EVAL":
            return [operands[0]] if operands else []
        case "DEFINE_MODULE":
            return [operands[0]] if operands else []
        case "PARALLEL_GATHER" | "ALL_GATHER" | "RACE_FIRST":
            return [operands[0]] if operands else []
        case _:
            return []


def dump_lir(program: LIRProgram) -> str:
    lines: list[str] = []
    if program.dialect != "compat":
        lines.append(f"dialect: {program.dialect}")
    for index, function in enumerate(program.functions):
        params = ", ".join(param.name for param in function.params)
        suffix = " [main]" if index == program.main else ""
        lines.append(
            f"fn#{index} {function.name.name}({params}) regs={function.register_count}{suffix}"
        )
        if function.frame_layout is not None:
            lines.append(f"  frame: {_format_frame_layout(function.frame_layout)}")
        for space in function.symbol_spaces:
            lines.append(f"  space: {_format_symbol_space(space)}")
        for continuation in function.continuations:
            lines.append(f"  continuation: {_format_continuation(continuation)}")
        for handler in function.handlers:
            lines.append(f"  handler: {_format_handler(handler)}")
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


def _format_instruction(instruction: LIRInstruction) -> str:
    if not instruction.operands:
        return instruction.opcode
    return (
        f"{instruction.opcode} {', '.join(_format_operand(item) for item in instruction.operands)}"
    )


def _format_operand(value: object) -> str:
    if isinstance(value, LIRBindingAddr):
        return f"s{value.space}.slot{value.slot}"
    if isinstance(value, Symbol):
        return value.name
    if isinstance(value, tuple):
        return f"({', '.join(_format_operand(item) for item in value)})"
    return repr(value)


def _format_frame_layout(value: LIRFrameLayout) -> str:
    pieces = [
        value.kind,
        value.name,
        f"regs={value.register_count}",
        f"slots={value.local_slot_count}",
    ]
    if value.ss_chain:
        pieces.append(f"ss=({_format_int_tuple(value.ss_chain)})")
    if value.saved_registers:
        pieces.append(f"saved=({_format_int_tuple(value.saved_registers)})")
    return " ".join(pieces)


def _format_symbol_space(value: LIRSymbolSpaceLayout) -> str:
    parent = "" if value.parent is None else f" parent=s{value.parent}"
    slots = ", ".join(
        f"{slot.symbol.name}@slot{slot.address.slot}:{slot.state}" for slot in value.slots
    )
    return f"s{value.id} {value.name}{parent} slots=[{slots}]"


def _format_continuation(value: LIRContinuationLayout) -> str:
    target = "<unknown>" if value.resume_target is None else str(value.resume_target)
    spaces = _format_int_tuple(value.saved_spaces)
    regs = _format_int_tuple(value.saved_registers)
    mode = "multi-shot" if value.multi_shot else "one-shot"
    return f"k{value.id} target={target} spaces=({spaces}) regs=({regs}) {mode}"


def _format_handler(value: LIRHandlerLayout) -> str:
    target = "<unknown>" if value.handler_target is None else str(value.handler_target)
    effects = ", ".join(effect.name for effect in value.effects)
    spaces = _format_int_tuple(value.ss_chain)
    parent = "" if value.parent_handler is None else f" parent=h{value.parent_handler}"
    return f"h{value.id} effects=[{effects}] target={target} ss=({spaces}){parent}"


def _format_int_tuple(values: tuple[int, ...]) -> str:
    return ", ".join(str(item) for item in values)


def _format_span(span: SourceSpan | None) -> str:
    if span is None:
        return ""
    return f" @ {span.format()}"
