# coding: utf-8
# QY_DELETE_AFTER_MIGRATION: target=qy/ir/lir/__init__.py
"""LIR (Low-level IR): linearized instruction sequence ready for register VM.

LIR is a low-level IR with its own opcode vocabulary, independent from bytecode.
It represents instructions after selection, scheduling, and register layout.
The bytecode compiler performs a structural mapping from LIR opcodes to bytecode
opcodes; LIR is free to express concepts bytecode cannot (e.g., LOAD_NIL).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from qy.diagnostics import Diagnostic
from qy.errors import SourceSpan
from qy.reader import Symbol

__all__ = [
    "LIRFunction",
    "LIRInstruction",
    "LIROpcode",
    "LIRProgram",
    "dump_lir",
    "verify_lir",
    # Abstract-machine types — re-exported from qy.ir.lir so that
    # "from qy.lir import LIRBindingAddr" works without needing qy.ir.lir.
    # qy.ir.lir defines the canonical types; qy.lir is the compat lowering source.
    "LIRBindingAddr",
    "LIRBindingSlot",
    "LIRBindingState",
    "LIRContinuationLayout",
    "LIRDialect",
    "LIRFrameKind",
    "LIRFrameLayout",
    "LIRHandlerLayout",
    "LIRInstructionIndex",
    "LIRRegister",
    "LIRSlotIndex",
    "LIRSymbolMeta",
    "LIRSymbolSpaceId",
    "LIRSymbolSpaceLayout",
]

# Lazy re-export to avoid circular import.
# Do NOT import from qy.ir.lir at module level here — qy.ir.lir imports from qy.lir.
def __getattr__(name: str):
    _ABSTRACT_MACHINE_TYPES = frozenset([
        "LIRBindingAddr", "LIRBindingSlot", "LIRBindingState",
        "LIRContinuationLayout", "LIRDialect", "LIRFrameKind",
        "LIRFrameLayout", "LIRHandlerLayout", "LIRInstructionIndex",
        "LIRRegister", "LIRSlotIndex", "LIRSymbolMeta",
        "LIRSymbolSpaceId", "LIRSymbolSpaceLayout",
    ])
    if name in _ABSTRACT_MACHINE_TYPES:
        from qy.ir.lir import __dict__ as d
        obj = d[name]
        globals()[name] = obj  # cache in globals to avoid future lookups
        return obj
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

# LIR has its own opcode vocabulary.  Some opcodes overlap with bytecode for
# simplicity, but LIR is free to add opcodes that have no direct bytecode
# equivalent (LOAD_NIL, LOAD_T, BRANCH_NIL).  The bytecode compiler maps
# LIR opcodes to bytecode opcodes during encoding.
LIROpcode = Literal[
    # -- Value loading --
    "LOAD_HOST",  # load arbitrary host value
    "LOAD_NIL",  # load QY_NIL (peephole from LOAD_HOST None)
    "LOAD_T",  # load QY_T
    "LOAD_ENV",  # load from environment by symbol
    "MOVE",  # register-to-register copy
    # -- Storage --
    "STORE_LOCAL",  # store into local scope
    "DEFINE_ONCE",  # define-once binding
    # -- Function construction --
    "MAKE_FUNCTION",  # create function value from index
    "MAKE_MACRO",  # create macro (compile-time only)
    # -- Scope --
    "ENTER_SCOPE",
    "EXIT_SCOPE",
    # -- Results --
    "APPEND_RESULT",
    # -- Data construction --
    "BUILD_TUPLE",
    # -- Calls --
    "CALL",  # non-tail call
    "TAIL_CALL",  # tail call (frame replacement)
    "APPLY",  # dynamic apply
    # -- Control flow --
    "JUMP",
    "JUMP_IF_FALSE",  # branch on _truthy (nil-only)
    "BRANCH_NIL",  # branch specifically on QY_NIL check (LIR-specific)
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
    frame_layout: object | None = None
    symbol_spaces: tuple[object, ...] = ()
    continuations: tuple[object, ...] = ()
    handlers: tuple[object, ...] = ()


@dataclass(frozen=True, slots=True)
class LIRProgram:
    functions: tuple[LIRFunction, ...]
    main: int = 0
    diagnostics: tuple[Diagnostic, ...] = ()
    dialect: Literal["compat", "abstract-machine"] = "compat"

    @property
    def ok(self) -> bool:
        return not any(diagnostic.severity == "error" for diagnostic in self.diagnostics)


_TERMINATORS = frozenset({"RETURN", "TAIL_CALL", "RAISE_EFFECT"})

# BRANCH_NIL also jumps but its target is the last operand, same as JUMP_IF_FALSE.
_JUMP_OPCODES = frozenset({"JUMP", "JUMP_IF_FALSE", "BRANCH_NIL"})


def verify_lir(program: LIRProgram) -> tuple[Diagnostic, ...]:
    """Structural verification of LIR program.

    Checks:
    - Every function ends with a terminator (RETURN / TAIL_CALL / RAISE_EFFECT).
    - No non-terminator instructions follow a terminator.
    - In abstract-machine dialect: rejects language-level effect opcodes (HANDLE/PERFORM/RESUME).
    - LOAD_HOST None should be LOAD_NIL (peephole missed).
    - Register operands are within [0, register_count).
    - Jump targets are within the instruction list.
    """
    diagnostics: list[Diagnostic] = []
    _LANGUAGE_LEVEL_EFFECT_OPCODES = frozenset({"HANDLE", "PERFORM", "RESUME"})
    for func in program.functions:
        if not func.instructions and func.name.name not in ("<lambda>",):
            diagnostics.append(
                Diagnostic(f"LIR function {func.name.name} has no instructions", severity="warning")
            )
            continue

        # Check terminator placement
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
            if inst.opcode == "LOAD_HOST" and len(inst.operands) >= 2 and inst.operands[1] is None:
                diagnostics.append(
                    Diagnostic(
                        f"LIR LOAD_HOST None at {func.name.name}:{idx} should be LOAD_NIL",
                        severity="warning",
                    )
                )
            # Check register operands are in range [0, register_count)
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
            # Check abstract-machine dialect does not retain language-level effect opcodes
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
            # Check jump targets are in range
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
    """Extract register operands from an instruction based on its opcode."""
    match opcode:
        case "LOAD_HOST" | "LOAD_NIL" | "LOAD_T" | "LOAD_ENV" | "RETURN" | "APPEND_RESULT":
            return [operands[0]] if operands else []
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


def _format_instruction(instruction: LIRInstruction) -> str:
    if not instruction.operands:
        return instruction.opcode
    return (
        f"{instruction.opcode} {', '.join(_format_operand(item) for item in instruction.operands)}"
    )


def _format_operand(value: object) -> str:
    if isinstance(value, Symbol):
        return value.name
    if isinstance(value, tuple):
        return f"({', '.join(_format_operand(item) for item in value)})"
    return repr(value)


def _format_span(span: SourceSpan | None) -> str:
    if span is None:
        return ""
    return f" @ {span.format()}"
