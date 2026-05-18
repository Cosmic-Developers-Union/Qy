# coding: utf-8
"""LLVM IR codegen — minimal end-to-end implementation.

Goal: compile `(echo "hello, world!")` to a working .ll file.

Architecture:
    LIRProgram -> emit_llvm_module() -> .ll
                       |
                       v
                  clang prog.c runtime/*.c -> a.out

Pipeline:
    source -> reader -> lowering -> MIR -> LIR -> llvm_codegen -> .ll
                                                               |
                                                               v
                                                      mqr.o (mqr.c)
                                                               |
                                                               v
                                                        clang -> a.out
"""

from __future__ import annotations

__all__ = [
    "compile_to_llvm_text",
    "emit_llvm_module",
]

# ---------------------------------------------------------------------------
# Builtin operators: Qy name -> (mqr_runtime_fn, arg_count)
# Only operators that can be called as first-class values need to be here.
# ---------------------------------------------------------------------------

BUILTIN_OPS: dict[str, tuple[str, int]] = {
    "+": ("mqr_add", 2),
    "-": ("mqr_sub", 2),
    "*": ("mqr_mul", 2),
    "/": ("mqr_div", 2),
    "=": ("mqr_eq", 2),
    "eq": ("mqr_eq", 2),
    "<": ("mqr_lt", 2),
    ">": ("mqr_gt", 2),
    "display": ("mqr_display", 1),
    "echo": ("mqr_echo", 1),
    "newline": ("mqr_newline", 0),
    "read": ("mqr_read", 0),
    "read-int": ("mqr_read_int", 0),
    "cons": ("mqr_cons", 2),
    "car": ("mqr_car", 1),
    "cdr": ("mqr_cdr", 1),
    "nil?": ("mqr_nil_p", 1),
    "not": ("mqr_not", 1),
}

BUILTIN_NAMES = list(BUILTIN_OPS.keys())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _escape(s: str) -> str:
    """Escape a string for LLVM IR constant."""
    return (
        s.replace("\\", "\\\\")
        .replace('"', "\\22")
        .replace("\n", "\\0A")
        .replace("\r", "\\0D")
        .replace("\t", "\\09")
    )


# ---------------------------------------------------------------------------
# Instruction emission
# ---------------------------------------------------------------------------


def _emit_instructions(fn, fn_idx: int, lines: list[str]) -> None:
    """Emit all instructions of one LIR function."""
    pc = 0
    while pc < len(fn.instructions):
        inst = fn.instructions[pc]
        ops = inst.operands
        opcode = inst.opcode

        # Emit block label if this PC is a jump target
        if pc > 0 and _is_jump_target(fn, pc):
            lines.append(f"block_{pc}:")
            lines.append("  br label %block_{pc}")

        match opcode:
            case "LOAD_NIL":
                dest = _dest(ops)
                if dest is not None:
                    lines.append(f"  %{dest} = call %qy_value @qy_nil()")

            case "LOAD_T":
                dest = _dest(ops)
                if dest is not None:
                    lines.append(f"  %{dest} = call %qy_value @qy_T()")

            case "LOAD_HOST":
                dest = _dest(ops)
                val = ops[1] if len(ops) > 1 else None
                if dest is None or val is None:
                    pc += 1
                    continue
                if isinstance(val, int):
                    lines.append(f"  %{dest} = call %qy_value @qy_int(i64 {val})")
                elif isinstance(val, float):
                    lines.append(f"  %{dest} = call %qy_value @qy_int(i64 {int(val)})")
                elif isinstance(val, str):
                    gname = _str_global(fn_idx, pc)
                    lines.append(
                        f"  %{dest} = call %qy_value @mqr_make_string("
                        f"i8* getelementptr inbounds ("
                        f"[{len(_escape(val)) + 1} x i8], "
                        f"[{len(_escape(val)) + 1} x i8]* {gname}, "
                        f"i32 0, i32 0), "
                        f"i64 {len(val)})"
                    )
                elif val is None:
                    lines.append(f"  %{dest} = call %qy_value @qy_nil()")
                else:
                    lines.append(f"  %{dest} = call %qy_value @qy_int(i64 0)")

            case "LOAD_ENV":
                dest = _dest(ops)
                sym = ops[1] if len(ops) > 1 else None
                sym_name = getattr(sym, "name", "?") if sym else "?"
                if dest is not None:
                    if sym_name in BUILTIN_OPS:
                        idx = BUILTIN_NAMES.index(sym_name)
                        lines.append(f"  %{dest} = call %qy_value @mqr_builtin_fn(i64 {idx})")
                    else:
                        # User symbol: resolve via mqr_resolve_sym
                        gname = _sym_global(fn_idx, pc, sym_name)
                        lines.append(
                            f"  %{dest} = call %qy_value @mqr_resolve_sym("
                            f"i8* getelementptr inbounds ("
                            f"[{len(sym_name) + 1} x i8], "
                            f"[{len(sym_name) + 1} x i8]* {gname}, "
                            f"i32 0, i32 0))"
                        )

            case "MOVE":
                dest = _dest(ops)
                src = ops[1] if len(ops) > 1 else None
                if dest is not None and src is not None:
                    lines.append(f"  %{dest} = load %qy_value, %qy_value* %reg_{src}")

            case "MAKE_FUNCTION":
                dest = _dest(ops)
                sub_idx = ops[1] if len(ops) > 1 else 0
                arity = ops[2] if len(ops) > 2 else 0
                if dest is not None:
                    lines.append(
                        f"  %{dest} = call %qy_value @mqr_make_function("
                        f"i64 {arity}, %qy_env* null, i64 {sub_idx})"
                    )

            case "MAKE_MACRO":
                dest = _dest(ops)
                if dest is not None:
                    lines.append(f"  %{dest} = call %qy_value @qy_nil()")

            case "ENTER_SCOPE" | "EXIT_SCOPE" | "STORE_LOCAL" | "DEFINE_ONCE":
                pass

            case "APPEND_RESULT":
                pass

            case "BUILD_TUPLE":
                dest = _dest(ops)
                elements = list(ops[1:]) if len(ops) > 1 else []
                if dest is not None and elements:
                    elements = list(reversed(elements))
                    first = True
                    for elem in elements:
                        if first:
                            lines.append(
                                f"  %{dest} = call %qy_value @mqr_cons("
                                f"%qy_value %{elem}, %qy_value @qy_nil())"
                            )
                            first = False
                        else:
                            lines.append(
                                f"  %{dest} = call %qy_value @mqr_cons("
                                f"%qy_value %{elem}, %qy_value %{dest})"
                            )

            case "CALL":
                dest = _dest(ops)
                callee = ops[1] if len(ops) > 1 else None
                args = list(ops[2]) if len(ops) > 2 and isinstance(ops[2], (list, tuple)) else []
                argc = len(args)
                if args:
                    lines.append(f"  %call.argv = alloca %qy_value, i64 {argc}")
                    for arg in args:
                        lines.append(f"  store %qy_value %{arg}, %qy_value* %call.argv")
                else:
                    lines.append("  %call.argv = inttoptr i64 0 to %qy_value*")
                if dest is not None:
                    lines.append(
                        f"  %{dest} = call %qy_value @mqr_call("
                        f"%qy_value %{callee}, %qy_value* %call.argv, i64 {argc})"
                    )
                else:
                    lines.append(
                        f"  call %qy_value @mqr_call("
                        f"%qy_value %{callee}, %qy_value* %call.argv, i64 {argc})"
                    )

            case "TAIL_CALL":
                callee = ops[0] if len(ops) > 0 else None
                args = list(ops[1]) if len(ops) > 1 and isinstance(ops[1], (list, tuple)) else []
                argc = len(args)
                if args:
                    lines.append(f"  %tail.argv = alloca %qy_value, i64 {argc}")
                    for arg in args:
                        lines.append(f"  store %qy_value %{arg}, %qy_value* %tail.argv")
                else:
                    lines.append("  %tail.argv = inttoptr i64 0 to %qy_value*")
                lines.append(
                    f"  %tail.ret = musttail call %qy_value @mqr_call("
                    f"%qy_value %{callee}, %qy_value* %tail.argv, i64 {argc})"
                )
                lines.append("  ret %qy_value %tail.ret")

            case "APPLY":
                dest = _dest(ops)
                if dest is not None:
                    lines.append(f"  %{dest} = call %qy_value @qy_nil()")

            case "JUMP":
                target = ops[-1] if ops else None
                if isinstance(target, int):
                    lines.append(f"  br label %block_{target}")
                else:
                    lines.append(f"  br label %block_{pc + 1}")

            case "JUMP_IF_FALSE":
                cond = ops[0] if len(ops) > 0 else None
                target = ops[-1] if len(ops) > 1 else None
                if isinstance(target, int) and cond is not None:
                    lines.append(f"  %cond.tag = extractvalue %qy_value %{cond}, 0")
                    lines.append("  %cond.nil_p = icmp eq i8 %cond.tag, 0")
                    lines.append(
                        f"  br i1 %cond.nil_p, label %block_{target}, label %block_{pc + 1}"
                    )
                else:
                    lines.append(f"  br label %block_{pc + 1}")

            case "BRANCH_NIL":
                target = ops[-1] if ops else None
                if isinstance(target, int):
                    lines.append(f"  br label %block_{target}")
                else:
                    lines.append(f"  br label %block_{pc + 1}")

            case "RETURN":
                val = ops[0] if ops else None
                if val is not None:
                    lines.append(f"  ret %qy_value %{val}")
                else:
                    lines.append("  ret %qy_value @qy_nil()")

            case "DEFEFFECT" | "PERFORM" | "HANDLE" | "RESUME":
                dest = _dest(ops)
                if dest is not None:
                    lines.append(f"  %{dest} = call %qy_value @qy_nil()")

            case "RAISE_EFFECT":
                lines.append(
                    "  call void @mqr_abort(i8* getelementptr "
                    "[6 x i8], [6 x i8]* @.str.ra, i32 0, i32 0)"
                )
                lines.append("  unreachable")

            case "PARALLEL_GATHER" | "ALL_GATHER" | "RACE_FIRST" | "CACHE_EVAL":
                dest = _dest(ops)
                if dest is not None:
                    lines.append(f"  %{dest} = call %qy_value @qy_nil()")

            case "DEFINE_MODULE" | "FROM_IMPORT":
                pass

            case "RUNTIME_EVAL":
                dest = _dest(ops)
                if dest is not None:
                    lines.append(f"  %{dest} = call %qy_value @qy_nil()")

            case _:
                dest = _dest(ops)
                if dest is not None:
                    lines.append(f"  %{dest} = call %qy_value @qy_nil()")

        pc += 1

    # Emit exit block if last instruction is not a unconditional JUMP/RETURN
    if fn.instructions:
        last = fn.instructions[-1]
        if last.opcode not in ("RETURN", "JUMP", "TAIL_CALL"):
            # Add exit label and return nil
            if _is_jump_target(fn, pc) or pc not in {i for i in range(len(fn.instructions))}:
                lines.append(f"block_{pc}:")
            lines.append("  ret %qy_value @qy_nil()")


def _dest(ops) -> int | None:
    return ops[0] if ops else None


def _is_jump_target(fn, pc: int) -> bool:
    for inst in fn.instructions:
        if inst.opcode in ("JUMP", "JUMP_IF_FALSE", "BRANCH_NIL"):
            if inst.operands and isinstance(inst.operands[-1], int) and inst.operands[-1] == pc:
                return True
    return False


# ---------------------------------------------------------------------------
# Global constant name helpers
# ---------------------------------------------------------------------------


def _str_global(fn_idx: int, pc: int) -> str:
    return f"@.str.fn{fn_idx}.pc{pc}"


def _sym_global(fn_idx: int, pc: int, sym: str) -> str:
    safe = sym.replace("-", "_").replace("?", "_p")
    return f"@.sym.fn{fn_idx}.pc{pc}.{safe}"


# ---------------------------------------------------------------------------
# Module emission
# ---------------------------------------------------------------------------

LLVM_HEADER = """; generated by qy llvm_codegen (minimal end-to-end)
; target: x86_64-unknown-linux-gnu / ABI: System V

target datalayout = "e-m:e-i64:64-f80:128-n8:16:32:64-S128"
target triple = "x86_64-unknown-linux-gnu"

; ---------------------------------------------------------------------------
; Qy tagged value
; ---------------------------------------------------------------------------
%qy_value = type {{ i8, [7 x i8] }}

; Environment (opaque in minimal impl)
%qy_env = type opaque

; Qy function pointer
%qy_fn = type %qy_value (i64, %qy_value*, %qy_env*)

; ---------------------------------------------------------------------------
; MQR runtime (from runtime/mqr.h)
; ---------------------------------------------------------------------------
declare %qy_value @qy_nil()
declare %qy_value @qy_T()
declare %qy_value @qy_int(i64)
declare i64 @mqr_add(i64, i64)
declare i64 @mqr_sub(i64, i64)
declare i64 @mqr_mul(i64, i64)
declare i64 @mqr_div(i64, i64)
declare %qy_value @mqr_eq(%qy_value, %qy_value)
declare %qy_value @mqr_lt(%qy_value, %qy_value)
declare %qy_value @mqr_gt(%qy_value, %qy_value)
declare void @mqr_print(%qy_value)
declare void @mqr_println(%qy_value)
declare void @mqr_display(%qy_value)
declare void @mqr_echo(%qy_value)
declare void @mqr_newline()
declare %qy_value @mqr_read()
declare %qy_value @mqr_read_int()
declare %qy_value @mqr_cons(%qy_value, %qy_value)
declare %qy_value @mqr_car(%qy_value)
declare %qy_value @mqr_cdr(%qy_value)
declare i8 @mqr_nil_p(%qy_value)
declare i8 @mqr_not(i8)
declare %qy_value @mqr_make_function(i64, %qy_env*, i64)
declare %qy_value @mqr_call(%qy_value, %qy_value*, i64)
declare %qy_value @mqr_make_string(i8*, i64)
declare i8* @mqr_string_cstr(%qy_value)
declare i64 @mqr_string_len(%qy_value)
declare %qy_value @mqr_resolve_sym(i8*)
declare %qy_value @mqr_builtin_fn(i64)
declare void @mqr_abort(i8*)
declare i8* @mqr_alloc(i64)
@_mqr_num_builtins = constant i64 {nb}

; extern Qy function table (populated by linker)
@qy_fn_table_size = external global i64

@.str.ra = private constant [6 x i8] c"raise\\00"
"""


def emit_llvm_module(lir_program) -> str:
    """Convert a LIRProgram to LLVM IR text.

    Minimal end-to-end: compile `(echo "hello, world!")`.
    """
    nb = len(BUILTIN_NAMES)
    lines: list[str] = []

    # Header
    lines.append(LLVM_HEADER.replace("{nb}", str(nb)))

    # Collect all constants first (so we emit them before functions)
    str_constants: list[tuple[str, str]] = []  # (gname, definition)
    sym_constants: list[tuple[str, str]] = []  # (gname, definition)
    const_emitted: set[str] = set()

    def _ensure_str(fn_idx: int, pc: int, val: str) -> str:
        gname = _str_global(fn_idx, pc)
        if gname not in const_emitted:
            escaped = _escape(val)
            const_emitted.add(gname)
            str_constants.append(
                (gname, f'{gname} = private constant [{len(escaped) + 1} x i8] c"{escaped}\\00"')
            )
        return gname

    def _ensure_sym(fn_idx: int, pc: int, sym: str) -> str:
        gname = _sym_global(fn_idx, pc, sym)
        if gname not in const_emitted:
            const_emitted.add(gname)
            sym_escaped = _escape(sym)
            sym_constants.append(
                (
                    gname,
                    f'{gname} = private constant [{len(sym_escaped) + 1} x i8] c"{sym_escaped}\\00"',
                )
            )
        return gname

    # Pass 1: collect constants (needed because _emit_instructions references gnames)
    # We do a dry run to collect constants, then emit them, then emit functions.
    # To avoid emitting instructions twice, we emit constants first with explicit
    # checks inside _emit_function.

    for fn_idx, fn in enumerate(lir_program.functions):
        for pc, inst in enumerate(fn.instructions):
            if inst.opcode == "LOAD_HOST" and len(inst.operands) > 1:
                val = inst.operands[1]
                if isinstance(val, str):
                    _ensure_str(fn_idx, pc, val)
            elif inst.opcode == "LOAD_ENV" and len(inst.operands) > 1:
                sym = inst.operands[1]
                sym_name = getattr(sym, "name", "?") if sym else "?"
                if sym_name not in BUILTIN_OPS:
                    _ensure_sym(fn_idx, pc, sym_name)

    # Emit all constants first
    for _, defn in str_constants:
        lines.append(defn)
    for _, defn in sym_constants:
        lines.append(defn)

    lines.append("")
    lines.append("; ====================================================================")
    lines.append("; Compiled Qy functions")
    lines.append("; ====================================================================")
    lines.append("")

    # Pass 2: emit functions
    for fn_idx, fn in enumerate(lir_program.functions):
        lines.append(
            f"define %qy_value @qy_fn_{fn_idx}(i64 %argc, %qy_value* %argv, %qy_env* %env) {{"
        )
        lines.append("entry:")

        # Load named parameters
        for i, p in enumerate(fn.params):
            lines.append(
                f"  %{p.name} = load %qy_value, %qy_value* %argv, !llvm.index !{{i32 {i}}}"
            )

        # Emit all instructions
        _emit_instructions(fn, fn_idx, lines)

        lines.append("}")

    return "\n".join(lines)


def compile_to_llvm_text(lir_program) -> str:
    """Convenience: compile a LIRProgram to LLVM IR text."""
    return emit_llvm_module(lir_program)
