# coding: utf-8
"""Emit WebAssembly text (WAT) from LIR.

设计：

- 每个 LIR function 编译成一个 wasm function，签名统一为
  ``(param i32 i32) (result i64)``（``argc``, ``argv``），这样所有可调用目标
  （内建算子 trampoline 与用户函数）都能放进同一张函数表，用
  ``call_indirect`` 动态调用。
- LIR 是扁平 CFG，wasm 需要结构化控制流；这里用经典的 ``loop`` +
  ``br_table`` dispatcher：``pc`` 是局部变量，每个 LIR 指令索引对应一个
  嵌套 ``block``，``br_table`` 的目标索引 ``i`` 落在该指令的代码起点。
- 寄存器是 wasm 局部变量 ``$r0..``；参数从 ``argv`` 载入；调用参数写入
  linear memory 的 scratch 栈（``$sp``）。
- 符号解析在编译期完成：参数 / 当前 scope 内 ``STORE_LOCAL`` / ``DEFINE_ONCE``
  绑定的寄存器、函数自身名（支持直接自递归）、数字字面量、``nil``/``T``、
  内建算子名。其余符号（模块/宿主绑定、闭包捕获的自由变量）暂不支持，会
  抛出 :class:`WasmUnsupportedError`，而不是静默编译成错误结果。

当前支持 int/nil/T/string、内建算术/IO、无自由变量的 defun/lambda、let、
cond/pipeline 控制流、CALL/TAIL_CALL（尚未做尾调用优化）；effect、module、
macro、并行、闭包捕获与深尾递归未支持。
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from typing import cast

from qy.backend.scalars import classify_constant
from qy.backend.wasm.abi import NUM_BUILTINS
from qy.backend.wasm.abi import VAL_NIL
from qy.backend.wasm.abi import VAL_T
from qy.backend.wasm.abi import builtin_index
from qy.backend.wasm.abi import callable_value
from qy.backend.wasm.abi import char_value
from qy.backend.wasm.abi import int_value
from qy.backend.wasm.abi import string_value
from qy.backend.wasm.abi import table_index_for_function
from qy.ir.lir import LIRFunction
from qy.ir.lir import LIRProgram

__all__ = ["WasmUnsupportedError", "emit"]

_MEMORY_PAGES = 64  # 4 MiB
_SCRATCH_BASE = 1 << 20  # 1 MiB，字符串数据段放在其下
_STRING_BASE = 1024

# 未实现（或当前宿主模型无法表达）的 opcode。
_UNSUPPORTED_OPCODES = frozenset(
    {
        "HANDLE",
        "PERFORM",
        "RESUME",
        "RAISE_EFFECT",
        "DEFEFFECT",
        "DEFINE_MODULE",
        "FROM_IMPORT",
        "MAKE_MACRO",
        "RUNTIME_EVAL",
        "CACHE_EVAL",
        "PARALLEL_GATHER",
        "ALL_GATHER",
        "RACE_FIRST",
        "BUILD_TUPLE",
        "APPLY",
        "FRAME_ENTER",
        "FRAME_LEAVE",
        "SS_ENTER",
        "SS_LEAVE",
        "SS_COPY",
        "SS_RESTORE",
        "SS_LOOKUP",
        "SLOT_READ",
        "SLOT_COMPLETE",
        "SLOT_PENDING_EFFORT",
        "CONT_CAPTURE",
        "CONT_COPY",
        "CONT_RESTORE",
        "CONT_INJECT",
        "HANDLER_PUSH",
        "HANDLER_POP",
        "EFFECT_UNWIND",
        "EFFECT_DISPATCH",
    }
)


class WasmUnsupportedError(Exception):
    """Raised when the LIR uses a construct the wasm backend cannot lower."""


@dataclass
class _StringPool:
    """UTF-8 string pool stored as ``[i32 length][bytes]`` data segments."""

    offset: int = _STRING_BASE
    segments: list[tuple[int, bytes]] = field(default_factory=list)

    def intern(self, text: str) -> int:
        encoded = text.encode("utf-8")
        address = self.offset
        self.segments.append((address, len(encoded).to_bytes(4, "little") + encoded))
        self.offset = (address + 4 + len(encoded) + 7) & ~7
        return address


@dataclass
class _FunctionEmitter:
    function: LIRFunction
    fn_idx: int
    pool: _StringPool

    def __post_init__(self) -> None:
        self.lines: list[str] = []
        # 环境绑定必须快照到专用 local：LIR 寄存器会被后续指令复用，
        # 直接把 `LOAD_ENV` 解析成某个寄存器会在覆盖后读到错误的值。
        self.env_slots = len(self.function.params) + sum(
            1
            for inst in self.function.instructions
            if inst.opcode in ("STORE_LOCAL", "DEFINE_ONCE")
        )
        self.env_cursor = 0
        self.scopes: list[dict[str, int]] = [{}]
        for param in self.function.params:
            self.scopes[0][param.name] = self.env_cursor
            self.env_cursor += 1

    def _bind(self, name: str, source_reg: object) -> None:
        slot = self.env_cursor
        self.env_cursor += 1
        self.scopes[-1][name] = slot
        self.out(f"    (local.set $e{slot} (local.get $r{source_reg}))")

    # -- helpers -------------------------------------------------------------

    def out(self, text: str) -> None:
        self.lines.append(text)

    def _value_expr(self, name: str) -> str | None:
        """Return a wasm value expression for a symbol, or None if unresolved."""
        for scope in reversed(self.scopes):
            if name in scope:
                return f"(local.get $e{scope[name]})"
        if name == self.function.name.name and name not in ("<main>", "<lambda>"):
            return f"(i64.const {callable_value(table_index_for_function(self.fn_idx))})"
        if name in ("true", "T"):
            return f"(i64.const {VAL_T})"
        if name in ("false", "nil", "none"):
            return f"(i64.const {VAL_NIL})"
        builtin = builtin_index(name)
        if builtin >= 0:
            return f"(i64.const {callable_value(builtin)})"
        try:
            integer = int(name)
        except ValueError:
            return None
        return f"(i64.const {int_value(integer)})"

    def _call_sequence(
        self,
        callee_reg: object,
        args: tuple,
        dest: object | None,
        *,
        tail: bool,
        builtin_id: int | None = None,
    ) -> None:
        argc = len(args)
        self.out("    (local.set $sp_save (global.get $sp))")
        for position, arg in enumerate(args):
            self.out(f"    (i64.store offset={position * 8} (global.get $sp) (local.get $r{arg}))")
        self.out(f"    (global.set $sp (i32.add (global.get $sp) (i32.const {argc * 8})))")
        if builtin_id is not None:
            # CALL_BUILTIN：内建下标由 LIR selection 决定，直接调用对应 trampoline，
            # 不再经过"物化 callable + call_indirect"。
            self.out(f"    (call $builtin_{builtin_id} (i32.const {argc}) (local.get $sp_save))")
        else:
            # call_indirect 从栈顶取 table index，因此 index 必须放在参数之后。
            self.out(
                "    (call_indirect (type $qyfn)"
                f" (i32.const {argc})"
                " (local.get $sp_save)"
                f" (i32.wrap_i64 (i64.shr_u (local.get $r{callee_reg}) (i64.const 3))))"
            )
        if tail:
            # 直接返回被调用者的结果；caller 会恢复它自己保存的 sp。
            self.out("    (return)")
            return
        if dest is None:
            self.out("    (drop)")
        else:
            self.out(f"    (local.set $r{dest})")
        self.out("    (global.set $sp (local.get $sp_save))")

    def _load_host(self, dest: object, value: object) -> None:
        kind, payload = classify_constant(value)
        if kind in ("nil", "none"):
            self.out(f"    (local.set $r{dest} (i64.const {VAL_NIL}))")
        elif kind == "t":
            self.out(f"    (local.set $r{dest} (i64.const {VAL_T}))")
        elif kind == "bool":
            self.out(f"    (local.set $r{dest} (i64.const {VAL_T if payload else VAL_NIL}))")
        elif kind == "int":
            self.out(f"    (local.set $r{dest} (i64.const {int_value(cast(int, payload))}))")
        elif kind == "char":
            self.out(f"    (local.set $r{dest} (i64.const {char_value(ord(cast(str, payload)))}))")
        elif kind == "string":
            address = self.pool.intern(cast(str, payload))
            self.out(f"    (local.set $r{dest} (i64.const {string_value(address)}))")
        else:
            raise WasmUnsupportedError(f"LOAD_HOST with unsupported value {value!r}")

    # -- instruction translation --------------------------------------------

    def emit_instruction(self, inst) -> None:
        opcode = inst.opcode
        ops = inst.operands

        if opcode == "JUMP":
            self.out(f"    (local.set $pc (i32.const {ops[-1]}))")
            self.out("    (br $dispatch)")
            return
        if opcode in ("JUMP_IF_FALSE", "BRANCH_NIL"):
            cond, target = ops[0], ops[-1]
            self.out(f"    (if (i64.eq (i64.and (local.get $r{cond}) (i64.const 7)) (i64.const 1))")
            self.out("      (then")
            self.out(f"        (local.set $pc (i32.const {target}))")
            self.out("        (br $dispatch)))")
            return

        if opcode in _UNSUPPORTED_OPCODES:
            raise WasmUnsupportedError(f"{opcode} is not supported by the wasm backend")

        match opcode:
            case "ENTER_SCOPE":
                self.scopes.append({})
            case "EXIT_SCOPE":
                if len(self.scopes) > 1:
                    self.scopes.pop()
            case "STORE_LOCAL" | "DEFINE_ONCE":
                self._bind(getattr(ops[0], "name", str(ops[0])), ops[1])
            case "MOVE":
                self.out(f"    (local.set $r{ops[0]} (local.get $r{ops[1]}))")
            case "LOAD_NIL":
                self.out(f"    (local.set $r{ops[0]} (i64.const {VAL_NIL}))")
            case "LOAD_T":
                self.out(f"    (local.set $r{ops[0]} (i64.const {VAL_T}))")
            case "LOAD_HOST":
                self._load_host(ops[0], ops[1] if len(ops) > 1 else None)
            case "LOAD_ENV":
                dest, symbol = ops[0], ops[1]
                name = getattr(symbol, "name", str(symbol))
                resolved = self._value_expr(name)
                if resolved is None:
                    raise WasmUnsupportedError(
                        f"unresolved symbol {name!r} in wasm backend"
                        " (closures/modules/host bindings are not supported yet)"
                    )
                self.out(f"    (local.set $r{dest} {resolved})")
            case "MAKE_FUNCTION":
                value = callable_value(table_index_for_function(ops[1]))
                self.out(f"    (local.set $r{ops[0]} (i64.const {value}))")
            case "APPEND_RESULT":
                self.out(f"    (call $append_result (local.get $r{ops[0]}))")
            case "CALL_BUILTIN":
                self._call_sequence(
                    None,
                    tuple(ops[2]) if len(ops) > 2 else (),
                    ops[0],
                    tail=False,
                    builtin_id=cast(int, ops[1]),
                )
            case "CALL":
                self._call_sequence(
                    ops[1], tuple(ops[2]) if len(ops) > 2 else (), ops[0], tail=False
                )
            case "TAIL_CALL":
                args = tuple(ops[1]) if len(ops) > 1 else ()
                self._call_sequence(ops[0], args, None, tail=True)
            case "RETURN":
                self.out(f"    (return (local.get $r{ops[0]}))")
            case _:
                raise WasmUnsupportedError(f"wasm backend does not handle opcode {opcode!r}")

    # -- function ------------------------------------------------------------

    def emit(self) -> str:
        register_count = self.function.register_count
        self.out(
            f"  (func $qy_fn_{self.fn_idx} (type $qyfn)"
            " (param $argc i32) (param $argv i32) (result i64)"
        )
        self.out("    (local $pc i32)")
        self.out("    (local $sp_save i32)")
        for index in range(register_count):
            self.out(f"    (local $r{index} i64)")
        for index in range(self.env_slots):
            self.out(f"    (local $e{index} i64)")
        for index in range(len(self.function.params)):
            self.out(f"    (local.set $e{index} (i64.load offset={index * 8} (local.get $argv)))")
        self.out("    (local.set $pc (i32.const 0))")
        self.out("    (loop $dispatch")

        count = len(self.function.instructions)
        for pc in range(count - 1, -1, -1):
            self.out(f"      (block $b{pc}")
        targets = " ".join(f"$b{pc}" for pc in range(count))
        self.out(f"        (br_table {targets} (local.get $pc))")

        # 经典 dispatcher：每个 block 的结束位置恰好落在对应 pc 的代码之前，
        # 因此 `br $bK` 会跳到 code K（close 在 code 之前发出）。
        for pc, inst in enumerate(self.function.instructions):
            self.out("      )")  # close block $b{pc}
            self.emit_instruction(inst)
            if inst.opcode not in ("JUMP", "JUMP_IF_FALSE", "BRANCH_NIL", "RETURN", "TAIL_CALL"):
                self.out(f"    (local.set $pc (i32.const {pc + 1}))")
                self.out("    (br $dispatch)")

        self.out("    )")  # loop
        self.out("    (unreachable)")
        self.out("  )")
        return "\n".join(self.lines)


def emit(lir_program: LIRProgram) -> str:
    """Lower a compat LIR program to WebAssembly text."""
    if lir_program.dialect != "compat":
        raise WasmUnsupportedError(
            f"wasm backend expects compat LIR, got dialect={lir_program.dialect!r}"
        )
    pool = _StringPool()
    functions = [
        _FunctionEmitter(function, fn_idx, pool).emit()
        for fn_idx, function in enumerate(lir_program.functions)
    ]

    builtins = [
        f"  (func $builtin_{index} (type $qyfn)\n"
        f"    (call $call_builtin (i64.const {index}) (local.get 0) (local.get 1)))"
        for index in range(NUM_BUILTINS)
    ]

    data = []
    for address, payload in pool.segments:
        escaped = "".join(f"\\{byte:02x}" for byte in payload)
        data.append(f'  (data (i32.const {address}) "{escaped}")')

    table_entries = " ".join(
        [f"$builtin_{index}" for index in range(NUM_BUILTINS)]
        + [f"$qy_fn_{index}" for index in range(len(lir_program.functions))]
    )

    lines = [
        "(module",
        '  (import "qy" "call_builtin" (func $call_builtin (param i64 i32 i32) (result i64)))',
        '  (import "qy" "append_result" (func $append_result (param i64)))',
        f'  (memory (export "memory") {_MEMORY_PAGES})',
        f"  (global $sp (mut i32) (i32.const {_SCRATCH_BASE}))",
        "  (type $qyfn (func (param i32 i32) (result i64)))",
        *builtins,
        *data,
        *[f"  (table {NUM_BUILTINS + len(lir_program.functions)} funcref)"],
        *[f"  (elem (i32.const 0) {table_entries})"],
        *functions,
        f'  (export "main" (func $qy_fn_{lir_program.main}))',
        ")",
    ]
    return "\n".join(lines) + "\n"
