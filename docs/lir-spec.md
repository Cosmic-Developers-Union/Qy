# Qy LIR 语言规范

## §0 目的与受众

本文档是 Qy LIR（Qy 抽象机 IR）的**正式语言规范**，是 LIR 形态的规范真源。它面向：

- 为 pipeline 的 LIR 阶段编写测试的工程师（可对照此文档断言 opcode 序列与 layout 形状）；
- 阅读 `qy/passes/lir/lower.py` / `linearize.py` / `compat_effects.py` / `effects.py` 的贡献者；
- 维护 register VM / LLVM backend 的工程师（这些后端消费 verified LIR）。

本文档规定：

- LIR 的 EBNF 文法（包含 `compat` 与 `abstract-machine` 两种 dialect）；
- 每个 opcode 的 operand 含义、不变量、dialect 归属；
- Layout 数据结构（symbol-space / frame / continuation / handler / slot）；
- LIR verifier 应当检查的不变量；
- MIR → LIR 的 lowering 映射（含 compat 折叠与目标 abstract-machine lowering 两套规则）。

本文档**不**规定：

- LIR→bytecode 的 emit（见 `docs/pipeline.md` §"Bytecode"）；
- 高层边界与设计意图（见 `docs/ir-design.md` §4 与 `docs/lir.md`）；
- register VM 内部状态机（见 `qy/backend/vm/spec/`）。

实现真源：`qy/ir/lir/node.py`、`qy/ir/lir/frame.py`、`qy/ir/lir/verify.py`、`qy/passes/lir/lower_pass.py`、`qy/passes/lir/lower.py`、`qy/passes/lir/linearize.py`、`qy/passes/lir/compat_effects.py`、`qy/passes/lir/effects.py`、`qy/passes/lir/verify.py`。

## §1 层定位

LIR 是**Qy 抽象机 IR**：低层、VM-facing、尚未最终编码，但已经把 Qy 语言执行机制完全显式化。

它**回答**：

- virtual stack 如何表示？
- continuation frame 如何捕获、复制、恢复？
- handler frame / effect marker 如何布局？
- symbol-space-chain 如何 enter / leave / copy / restore？
- binding slot 如何 lookup / read / complete / report pending？
- MIR 的 effect edge 如何变成 CFG jump + ss-chain transition？
- 物理寄存器 / frame / continuation / host ABI 怎么布局？
- 哪些 fixup、peephole、debug 注入应该在编码前完成？

它**不**回答：

- source-level binding 是什么；
- macro 是什么；
- HIR structured semantics 是什么；
- bytecode 的最终二进制或序列化格式是什么。

```text
MIR 描述程序控制流；
LIR 描述 Qy 抽象机器如何执行这些控制流。
```

### 1.1 Dialect

LIR 携带 `dialect ∈ {"compat", "abstract-machine"}`：

- **`compat`**（当前生产路径）：保留 `HANDLE` / `PERFORM` / `RESUME` 等语言级 effect opcode；register VM 直接解释。这是迁移期的实现选择。
- **`abstract-machine`**（目标）：禁止保留语言级 effect opcode；`EFFECT_*` placeholder 必须被 lowering 为 `HANDLER_PUSH/POP`、`CONT_CAPTURE/RESTORE`、`EFFECT_UNWIND/DISPATCH`、`SLOT_READ/COMPLETE`、`SS_ENTER/LEAVE/COPY/RESTORE`、`FRAME_ENTER/LEAVE` 等抽象机操作。`LLVM` / `libqy` 等后端可以从此 dialect 直接生成代码。

`abstract-machine` dialect 当前**未被 production 启用**——见 §7。

边界与设计意图详见 `docs/ir-design.md` §4、`docs/lir.md`。

## §2 EBNF 文法

### Legend

- `xxx?` 零或一次
- `xxx*` 零或多次
- `xxx+` 一或多次
- **粗体**：保留字
- `Symbol`、`SourceSpan`、`Diagnostic`：复用类型

### 2.1 顶层

```text
LIRProgram    := "LIRProgram" "{"
                    "functions"   ":" LIRFunction+ ","
                    "main"        ":" int "= 0" ","
                    "dialect"     ":" 'compat' | 'abstract-machine' "= 'compat'" ","
                    "diagnostics" ":" Diagnostic* "}"

LIRFunction   := "LIRFunction" "{"
                    "name"           ":" Symbol ","
                    "params"         ":" Symbol+ ","
                    "register_count" ":" int ","
                    "instructions"   ":" LIRInstruction+ ","
                    "frame_layout"   ":" LIRFrameLayout?  "= None" ","
                    "symbol_spaces"  ":" LIRSymbolSpaceLayout* "= ()" ","
                    "continuations"  ":" LIRContinuationLayout* "= ()" ","
                    "handlers"       ":" LIRHandlerLayout* "= ()" "}"

LIRInstruction := "LIRInstruction" "{"
                      "opcode"     ":" LIROpcode ","
                      "operands"   ":" Any* ","
                      "span"       ":" SourceSpan? ","
                      "continuous" ":" bool "= false" "}"
```

派生属性：`LIRProgram.ok` 当且仅当 `diagnostics` 中无 `severity == "error"`。

### 2.2 Layout 数据结构

```text
LIRSymbolSpaceId    := int
LIRSlotIndex        := int
LIRRegister         := int
LIRInstructionIndex := int

LIRBindingState     := "declared" | "pending" | "completed" | "poisoned"

LIRBindingAddr      := "LIRBindingAddr" "{" "space" ":" LIRSymbolSpaceId "," "slot" ":" LIRSlotIndex "}"

LIRSymbolMeta       := "LIRSymbolMeta" "{" "symbol" ":" Symbol "," "span" ":" SourceSpan? "," "flags" ":" string* "}"

LIRBindingSlot      := "LIRBindingSlot" "{"
                          "address"         ":" LIRBindingAddr ","
                          "symbol"          ":" Symbol ","
                          "state"           ":" LIRBindingState "= 'declared'" ","
                          "metadata_index"  ":" int? "}"

LIRSymbolSpaceLayout := "LIRSymbolSpaceLayout" "{"
                          "id"       ":" LIRSymbolSpaceId ","
                          "name"     ":" string ","
                          "parent"   ":" LIRSymbolSpaceId? "= None" ","
                          "slots"    ":" LIRBindingSlot* ","
                          "metadata" ":" LIRSymbolMeta* "}"

LIRFrameKind        := "function" | "continuation" | "handler" | "task"

LIRFrameLayout      := "LIRFrameLayout" "{"
                          "kind"             ":" LIRFrameKind ","
                          "name"             ":" string ","
                          "register_count"   ":" int ","
                          "local_slot_count" ":" int "= 0" ","
                          "ss_chain"         ":" LIRSymbolSpaceId* "= ()" ","
                          "saved_registers"  ":" LIRRegister* "= ()" "}"

LIRContinuationLayout := "LIRContinuationLayout" "{"
                            "id"             ":" int ","
                            "resume_target"  ":" LIRInstructionIndex? "= None" ","
                            "saved_registers":" LIRRegister* "= ()" ","
                            "saved_spaces"   ":" LIRSymbolSpaceId* "= ()" ","
                            "multi_shot"     ":" bool "= true" "}"

LIRHandlerLayout    := "LIRHandlerLayout" "{"
                          "id"            ":" int ","
                          "effects"       ":" Symbol+ "= ()" ","
                          "handler_target":" LIRInstructionIndex? "= None" ","
                          "parent_handler":" int? "= None" ","
                          "ss_chain"      ":" LIRSymbolSpaceId* "= ()" "}"
```

### 2.3 opcode 字面集

```text
LIROpcode        :=  -- value / register (both)
                     "LOAD_HOST" | "LOAD_NIL" | "LOAD_T" | "LOAD_ENV" | "MOVE"
                  |  -- storage (both)
                     "STORE_LOCAL" | "DEFINE_ONCE"
                  |  -- function construction (both)
                     "MAKE_FUNCTION" | "MAKE_MACRO" | "APPLY" | "CALL" | "TAIL_CALL"
                  |  -- scope (both)
                     "ENTER_SCOPE" | "EXIT_SCOPE"
                  |  -- control (both)
                     "JUMP" | "JUMP_IF_FALSE" | "BRANCH_NIL" | "RETURN"
                  |  -- data / result (both)
                     "BUILD_TUPLE" | "APPEND_RESULT"
                  |  -- effect language-level (compat only)
                     "HANDLE" | "PERFORM" | "RESUME"
                  |  -- effect MIR placeholders (compat only)
                     "EFFECT_HANDLE_BEGIN" | "EFFECT_HANDLE_END" | "EFFECT_PERFORM" | "EFFECT_RESUME"
                  |  -- effect common (both)
                     "DEFEFFECT" | "RAISE_EFFECT"
                  |  -- concurrency (compat only)
                     "PARALLEL_GATHER" | "ALL_GATHER" | "RACE_FIRST" | "CACHE_EVAL"
                  |  -- module (both)
                     "DEFINE_MODULE" | "FROM_IMPORT"
                  |  -- meta (compat only)
                     "RUNTIME_EVAL"
                  |  -- abstract machine: frame / ss-chain (abstract-machine only)
                     "FRAME_ENTER" | "FRAME_LEAVE"
                  | "SS_ENTER" | "SS_LEAVE" | "SS_COPY" | "SS_RESTORE" | "SS_LOOKUP"
                  |  -- abstract machine: slot (abstract-machine only)
                     "SLOT_READ" | "SLOT_COMPLETE" | "SLOT_PENDING_EFFORT"
                  |  -- abstract machine: continuation / handler (abstract-machine only)
                     "CONT_CAPTURE" | "CONT_COPY" | "CONT_RESTORE" | "CONT_INJECT"
                  | "HANDLER_PUSH" | "HANDLER_POP"
                  | "EFFECT_UNWIND" | "EFFECT_DISPATCH"
```

完整列表见 `qy/ir/lir/node.py:79-151`。每条 opcode 的语义、operand 含义、dialect 归属见 §3。

## §3 opcode 目录

按家族分小节。每条 opcode 给出：**dialect 归属**、**语法形状**（operand 模板）、**字段语义**、**不变量**。

dialect 归属图例：

- `compat`：当前 production 路径使用（`compat_effects` 输出）。
- `abstract-machine`：目标 dialect，由 `lower_effects` 产出；当前未启用（见 §7）。
- `both`：两个 dialect 都允许保留。

### 3.1 Value / Register（both）

#### LOAD_HOST

```text
LOAD_HOST dst: LIRRegister, value: Any
```

| 字段 | 含义 |
| --- | --- |
| `dst` | 目标寄存器 |
| `value` | 直接嵌入的宿主对象；当前由 `linearize.py:39-42` 从 `LOAD_CONST` + pool 改写得到 |

#### LOAD_NIL / LOAD_T

```text
LOAD_NIL dst: LIRRegister
LOAD_T   dst: LIRRegister
```

Qy `nil` / `t` 字面加载。

#### LOAD_ENV

```text
LOAD_ENV dst: LIRRegister, symbol: Symbol
```

按 `symbol` 在当前 symbol-space-chain 中查找 binding；找不到则走 pending effort。

**目标 lowering**（abstract-machine）：静态可解析 → `SLOT_READ slot-addr`；pending → `SLOT_PENDING_EFFORT`。

**当前生产**：保留为 `LOAD_ENV`，VM 自行处理；这是 §7 关键事实 4。

#### MOVE

```text
MOVE dst: LIRRegister, src: LIRRegister
```

寄存器间复制。

### 3.2 Storage（both）

#### STORE_LOCAL

```text
STORE_LOCAL symbol: Symbol, src: LIRRegister
```

同 MIR 语义（§3.2 in mir-spec）。

#### DEFINE_ONCE

```text
DEFINE_ONCE name: Symbol, src: LIRRegister
```

**目标 lowering**：`SLOT_COMPLETE slot-addr, src`。**当前**：pass-through。

### 3.3 Function construction（both）

#### MAKE_FUNCTION

```text
MAKE_FUNCTION dst: LIRRegister, fn_idx: int
```

#### MAKE_MACRO

```text
MAKE_MACRO dst: LIRRegister, name: Symbol, params: tuple[Symbol, ...], raw_body: tuple[Any, ...]
```

#### APPLY

```text
APPLY dst: LIRRegister, fn_reg: LIRRegister, args_reg: LIRRegister
```

#### CALL

```text
CALL dst: LIRRegister, fn_reg: LIRRegister, args: tuple[LIRRegister, ...]
```

#### TAIL_CALL

```text
TAIL_CALL fn_reg: LIRRegister, args: tuple[LIRRegister, ...]
```

不增长 call stack。

### 3.4 Scope（both）

#### ENTER_SCOPE / EXIT_SCOPE

```text
ENTER_SCOPE
EXIT_SCOPE
```

**目标 lowering**：`SS_ENTER space-id` / `SS_LEAVE space-id`（与 frame pairing 一致）。**当前**：pass-through。

### 3.5 Control（both）

#### JUMP

```text
JUMP target: LIRInstructionIndex
```

无条件跳转。`target` 是绝对 instruction index，由 `_patch_jumps`（`linearize.py:96-99`）改写。

#### JUMP_IF_FALSE

```text
JUMP_IF_FALSE cond: LIRRegister, target: LIRInstructionIndex
```

`cond` 为 Qy `nil` 时跳转。由 `linearize.py:60-65` 从 MIR `BRANCH` 折叠。

#### BRANCH_NIL

```text
BRANCH_NIL cond: LIRRegister, true_target: LIRInstructionIndex, false_target: LIRInstructionIndex
```

显式三分支。**当前未被使用**（保留供 LLVM 等后端）；`JUMP_IF_FALSE` + `JUMP` 是 compat 折叠结果。

#### RETURN

```text
RETURN src: LIRRegister?
```

### 3.6 Data / Result（both）

#### BUILD_TUPLE

```text
BUILD_TUPLE dst: LIRRegister, regs: LIRRegister+
```

#### APPEND_RESULT

```text
APPEND_RESULT src: LIRRegister
```

### 3.7 Effect — language-level（compat only，当前实际生效）

#### HANDLE

```text
HANDLE dst_reg: LIRRegister, body_fn_idx: int, specs: tuple[EffectSpec, ...]
```

由 `compat_effects.py:60-66` 从配对 `EFFECT_HANDLE_BEGIN/END` 折叠产生。

#### PERFORM

```text
PERFORM dst_reg: LIRRegister, effect: Symbol, arg_reg: LIRRegister
```

由 `compat_effects.py:69-75` 从 `EFFECT_PERFORM` 折叠；其后追加 `JUMP new_target`（resume target），fall-through 时省略。

#### RESUME

```text
RESUME dst_reg: LIRRegister, cont_reg: LIRRegister, value_reg: LIRRegister
```

由 `compat_effects.py:76-78` 从 `EFFECT_RESUME` 折叠（rename）。

### 3.8 Effect — MIR placeholders（compat only，被折叠）

`EFFECT_HANDLE_BEGIN` / `EFFECT_HANDLE_END` / `EFFECT_PERFORM` / `EFFECT_RESUME` 由 MIR lowering 产出（见 `mir-spec.md` §3.5）；`compat_effects` pass 把它们折叠为语言级 `HANDLE` / `PERFORM` / `RESUME`。最终 LIR 中不得保留这四个 placeholder（除非 dialect 切换为 abstract-machine）。

### 3.9 Effect — common（both）

#### DEFEFFECT

```text
DEFEFFECT name: Symbol, resumable: bool
```

#### RAISE_EFFECT

```text
RAISE_EFFECT effect: Symbol, arg_reg: LIRRegister, resumable: bool
```

### 3.10 Concurrency（compat only）

#### PARALLEL_GATHER / ALL_GATHER / RACE_FIRST

```text
PARALLEL_GATHER dst: LIRRegister, fn_indices: int+
ALL_GATHER       dst: LIRRegister, fn_indices: int+
RACE_FIRST       dst: LIRRegister, fn_indices: int+
```

目标 dialect 应通过 `task frame` + join 协议表达；本 spec 仅占位。

#### CACHE_EVAL

```text
CACHE_EVAL dst: LIRRegister, cache_key: Any, thunk_fn_idx: int
```

### 3.11 Module（both）

#### DEFINE_MODULE

```text
DEFINE_MODULE dst: LIRRegister, name: Symbol, body_fn_idx: int, exports: tuple[Symbol, ...]
```

#### FROM_IMPORT

```text
FROM_IMPORT module: Symbol, specs: tuple[ImportSpec, ...]
```

### 3.12 Meta（compat only）

#### RUNTIME_EVAL

```text
RUNTIME_EVAL dst: LIRRegister, inner_reg: LIRRegister
```

### 3.13 Abstract machine — frame / ss-chain（abstract-machine only）

#### FRAME_ENTER / FRAME_LEAVE

```text
FRAME_ENTER frame_layout: LIRFrameLayout
FRAME_LEAVE frame_layout: LIRFrameLayout
```

进入 / 离开 function frame；绑定到 `frame_layout` 的 register segment / ss_chain / saved registers。

#### SS_ENTER / SS_LEAVE

```text
SS_ENTER space_id: LIRSymbolSpaceId
SS_LEAVE space_id: LIRSymbolSpaceId
```

symbol-space-chain 推入 / 弹出。

#### SS_COPY / SS_RESTORE / SS_LOOKUP

```text
SS_COPY    dst_chain: LIRRegister, src_chain: LIRRegister
SS_RESTORE chain: LIRRegister
SS_LOOKUP  dst: LIRRegister, symbol: Symbol, chain: LIRRegister
```

- `SS_COPY` 复制当前 ss-chain；用于 multi-shot continuation。
- `SS_RESTORE` 把 ss-chain 恢复到 `chain`。
- `SS_LOOKUP` 在给定 chain 中按 symbol 查找 binding。

> 当前实现**不 emit** 这三个 opcode；`linearize.py` 与 `effects.py` 均未触达。`SS_LOOKUP` 是 `LIROpcode` 中的声明但尚未被任何 lowering pass 调用。

### 3.14 Abstract machine — slot（abstract-machine only）

#### SLOT_READ

```text
SLOT_READ dst: LIRRegister, slot_addr: LIRBindingAddr
```

读取 slot 当前值；若 slot state 为 `pending` 应走 `SLOT_PENDING_EFFORT`。

#### SLOT_COMPLETE

```text
SLOT_COMPLETE slot_addr: LIRBindingAddr, value_reg: LIRRegister
```

把 slot state 转为 `completed`。重复 `SLOT_COMPLETE` 是 verifier / runtime error。

#### SLOT_PENDING_EFFORT

```text
SLOT_PENDING_EFFORT dst: LIRRegister, slot_addr: LIRBindingAddr
```

读 pending slot 时的 effort 操作；不是 Python exception 的偶然行为。

### 3.15 Abstract machine — continuation / handler（abstract-machine only）

#### CONT_CAPTURE

```text
CONT_CAPTURE cont_reg: LIRRegister, cont_layout_id: int,
             resume_target: LIRInstructionIndex?, saved_registers: LIRRegister*,
             dst: LIRRegister, resumable: bool
```

捕获 delimited continuation；填充 `LIRContinuationLayout`。

#### CONT_COPY / CONT_RESTORE / CONT_INJECT

```text
CONT_COPY    dst: LIRRegister, src: LIRRegister
CONT_RESTORE cont: LIRRegister, dst: LIRRegister, value: LIRRegister
CONT_INJECT  cont: LIRRegister, value_reg: LIRRegister
```

- `CONT_COPY` 复制 continuation（multi-shot 默认）。
- `CONT_RESTORE` 恢复 continuation 并把 `value` 注入 `resume_target`；它是**非终结指令**（与 compat `RESUME` 一致）：resume 的结果写回 `dst`，handler body 继续执行。这样 `(+ (resume k a) (resume k b))` 这类组合 resume 才能成立。
- `CONT_INJECT` 仅注入 value；当前**未被任何 lowering pass emit**（即使 `effects.py` 也不 emit；见 §7 关键事实 6）。

#### HANDLER_PUSH / HANDLER_POP

```text
HANDLER_PUSH handler_layout_id: int, target: LIRInstructionIndex?,
              parent_handler: int?, specs: tuple[EffectSpec, ...]
HANDLER_POP  handler_layout_id: int
```

在 virtual stack 上推入 / 弹出 effect handler。

#### EFFECT_UNWIND / EFFECT_DISPATCH

```text
EFFECT_UNWIND    effect: Symbol, arg_reg: LIRRegister, cont_reg: LIRRegister
EFFECT_DISPATCH  handler_fn_reg: LIRRegister, handler_layout_id: int,
                 arg_reg: LIRRegister, cont_reg: LIRRegister
```

- `EFFECT_UNWIND` 把控制权转交给最近匹配 handler。
- `EFFECT_DISPATCH` 在 handler 入口调用 handler 函数。

> **未定义的 opcode**：`HANDLER_FIND` 是 `LIROpcode` 字面集中的声明，但**未被任何 lowering pass emit**；`effects.py` 直接产生 `HANDLER_PUSH` 与 `HANDLER_POP`，不经过 `HANDLER_FIND`。

## §4 Verifier 规则

实现：`qy/ir/lir/verify.py`，由 `qy/passes/lir/verify.py` 调用。

| 编号 | 不变量 |
| --- | --- |
| L1 | 每个 `LIRFunction.register_count` 与所有 operand 中的 register index 一致（< register_count） |
| L2 | 同一 `LIRProgram` 内 function id 唯一；main 合法 |
| L3 | instruction operand kind 与 opcode 一致（`_register_operands_of` 表） |
| L4 | `JUMP` / `JUMP_IF_FALSE` / `BRANCH_NIL` 的 target 是合法 instruction index |
| L5 | `LIRFrameLayout` 的 register_count / local_slot_count / saved_registers 合法 |
| L6 | `LIRContinuationLayout` 的 saved_registers / saved_spaces 与所在函数布局一致 |
| L7 | `LIRHandlerLayout.parent_handler` 指向同一 `LIRProgram` 内存在的 handler |
| L8 | `LIRBindingSlot.address` 指向存在的 `LIRSymbolSpaceLayout` |
| L9 | 同一 slot 至多一次 `SLOT_COMPLETE` |
| L10 | `ENTER_SCOPE` / `EXIT_SCOPE` 嵌套正确 |
| L11 | `HANDLER_PUSH` / `HANDLER_POP` 嵌套正确 |
| L12 | `FRAME_ENTER` / `FRAME_LEAVE` 嵌套正确 |
| L13 | 当 `dialect == "abstract-machine"` 时，最终指令流中**不得**保留 `PERFORM` / `HANDLE` / `RESUME` 或 `EFFECT_HANDLE_BEGIN/END` / `EFFECT_PERFORM` / `EFFECT_RESUME`（`verify.py:96-105`） |
| L14 | 当 `dialect == "compat"` 时，`abstract-machine only` opcode（FRAME_*/SS_*/SLOT_*/CONT_*/HANDLER_PUSH/POP/EFFECT_UNWIND/EFFECT_DISPATCH）不得出现 |
| L15 | `_verify_continuous_run`（`verify.py:153-199`）：`continuous=True` 指令不得是 break-point opcode；同一指令流不得与 break-point opcode 相邻 |

`break-point opcode` 集合见 `_CONTINUOUS_BREAK_OPCODES`（`qy/ir/lir/verify.py:26-58`），包含 scope / handler / effect / frame / ss-chain 切换与 join opcode。

## §5 MIR → LIR 映射

**实现真源**：

- Driver：`qy/passes/lir/lower.py:36-50` 的固定管线；
- 步骤 1：`linearize.py:22-35 linearize_function`；
- 步骤 2：`compat_effects.py:32 lower_compat_effects`；
- 步骤 3：`peephole.py`；
- 步骤 4：`compact.py compact_registers`。

**目标 abstract-machine lowering**：`effects.py:81 lower_effects`，**当前未被 driver 调用**（见 §7 关键事实 3）。

### 5.1 固定管线（当前 production）

```text
linearize_function → lower_compat_effects → peephole → compact_registers
```

每步对指令流做单向改写；最终 dialect 标记为 `"compat"`。

### 5.2 linearize_function 改写

| MIR | LIR | 实现位置 |
| --- | --- | --- |
| `LOAD_CONST dst, pool_idx` | `LOAD_HOST dst, value`（从 pool 取值） | `linearize.py:39-42` |
| 任何其他 MIR instruction | 整体 pass-through：`LIRInstruction(opcode, operands, span)` | `linearize.py:43` |
| `RETURN terminator` | `RETURN` | `linearize.py:51-53` |
| `TAIL_CALL terminator` | `TAIL_CALL` | `linearize.py:54-55` |
| `JUMP target_block` | `JUMP None`（target 由 `_patch_jumps` 改写为绝对 index） | `linearize.py:56-59, 96-99` |
| `BRANCH cond, true, false` | `JUMP_IF_FALSE cond, None` + `JUMP None`（true/false 改写） | `linearize.py:60-65` |
| `RAISE_EFFECT sym, msg, resumable` | `RAISE_EFFECT` | `linearize.py:66-69` |
| `EFFECT_PERFORM dst, eff, arg, resume_block, resumable` | `EFFECT_PERFORM dst, eff, arg, None, resumable`（resume_block 改写为绝对 index） | `linearize.py:70-82, 93-97` |

### 5.3 compat_effects 折叠

`lower_compat_effects`（`compat_effects.py`）只处理 effect placeholder；其他指令 pass-through。

| MIR/LIR placeholder | Compat LIR 输出 | 实现位置 |
| --- | --- | --- |
| `EFFECT_HANDLE_BEGIN handle_id, body_fn, specs` + 配对 `EFFECT_HANDLE_END handle_id, dst_reg` | 单条 `HANDLE dst_reg, body_fn, specs`（END 折叠） | `compat_effects.py:60-66` |
| `EFFECT_PERFORM dst, eff, arg, resume_idx, resumable` | `PERFORM dst, eff, arg` + trailing `JUMP new_target`（resume_idx 重映射；跳转 fall-through 时省略 JUMP） | `compat_effects.py:69-75, 103-134` |
| `EFFECT_RESUME dst, cont, value` | `RESUME dst, cont, value`（rename） | `compat_effects.py:76-78` |
| 其他 | copy through | `compat_effects.py:79-80` |

`old_to_new` 重映射所有 `JUMP` / `JUMP_IF_FALSE` 的 target（`compat_effects.py:89-101`）。

### 5.4 目标 abstract-machine lowering（dormant）

`effects.py:81 lower_effects` 把 EFFECT_* placeholder 替换为 abstract-machine 操作；当前未被 driver 调用。

| MIR/LIR placeholder | Abstract-machine LIR 输出 | 实现位置 |
| --- | --- | --- |
| `EFFECT_HANDLE_BEGIN(h, body_fn, specs)` | `HANDLER_PUSH h, target=None-patched, parent_id_or_-1, specs` + `MAKE_FUNCTION body_reg, body_fn_idx` + `CALL dst, body_reg, ()` + `HANDLER_POP h` + placeholder `JUMP None`（over dispatch tail） + dispatch tail：`EFFECT_DISPATCH handler_fn_reg, h, arg_reg, cont_reg` + `CALL dst, handler_fn_reg, (arg_reg, cont_reg)` + `HANDLER_POP h`；追加 `LIRHandlerLayout` | `effects.py:144-206` |
| `EFFECT_HANDLE_END(h, dst)` | 无新 instruction；把 over-region `JUMP` 改写到 `after_region_new_idx`；`old_to_new[end_idx]` = `after_region_new_idx` | `effects.py:208-226` |
| `EFFECT_PERFORM(dst, eff, arg, resume_idx, resumable)` | `CONT_CAPTURE cont_reg, cont_layout_id, None, (), dst, resumable` + `EFFECT_UNWIND eff, arg, cont_reg`；追加 `LIRContinuationLayout` | `effects.py:228-265` |
| `EFFECT_RESUME(dst, cont, value)` | `CONT_COPY cont_copy, cont` + `CONT_RESTORE cont_copy, dst, value` | `effects.py:267-276` |

目标 lowering 完毕后 `old_to_new` 重映射 `HANDLER_PUSH.handler_target` 与 `CONT_CAPTURE.resume_target`（`effects.py:283-317`）。

> **one-shot 优化**：spec 描述 `EFFECT_RESUME` 在 one-shot 时可省略 `CONT_COPY`，但 `effects.py:267-276` 当前**无条件 emit `CONT_COPY`**；one-shot 优化未实现。

### 5.5 目标 lowering（slot / frame，未实现）

| MIR/LIR | 目标 abstract-machine 输出 | 当前实现 |
| --- | --- | --- |
| `LOAD_ENV symbol`（静态可解析） | `SLOT_READ slot-addr`；pending → `SLOT_PENDING_EFFORT` | pass-through（事实 4） |
| `DEFINE_ONCE symbol value-reg` | `SLOT_COMPLETE slot-addr, value-reg` | pass-through |
| `ENTER_SCOPE` / `EXIT_SCOPE` | `SS_ENTER space-id` / `SS_LEAVE space-id` | pass-through |

这些 lowering **当前没有实现**。需要后续 pass（例如 `symbol_space_layout` / `binding_lowering`）补齐。

### 5.6 其他 pass-through

下列 MIR opcode 在 LIR 阶段保持原 opcode（仅经过 `peephole` / `compact`）：

```text
STORE_LOCAL, MAKE_FUNCTION, MAKE_MACRO, APPLY, CALL, TAIL_CALL,
DEFINE_MODULE, FROM_IMPORT, BUILD_TUPLE,
DEFEFFECT, RAISE_EFFECT,
PARALLEL_GATHER, ALL_GATHER, RACE_FIRST, CACHE_EVAL,
RUNTIME_EVAL, APPEND_RESULT, LOAD_NIL, LOAD_T, MOVE
```

## §6 工作样例

### 6.1 算术（compat LIR）

**MIR**（取自 `mir-spec.md` §6.1）：

```text
fn#0 main() entry=bb0 regs=3 [main]
  bb0:
    r0 = LOAD_CONST 0
    r1 = LOAD_CONST 1
    r2 = CALL r<+> (r0, r1)
    RETURN r2
```

**compat LIR**（伪 dump 风格与 `dump_lir` 一致）：

```text
fn#0 main() regs=3 [main]
  0000: LOAD_HOST r0, 1
  0001: LOAD_HOST r1, 2
  0002: CALL r2, r<+>, (r0, r1)
  0003: RETURN r2
```

要点：

- `LOAD_CONST 0 / 1` 被 `linearize.py:39-42` 改写为 `LOAD_HOST r0, 1` / `LOAD_HOST r1, 2`；
- 其他 MIR instruction pass-through；
- dialect 仍为 `"compat"`，但该函数不涉及 effect，因此 compat/abstract-machine opcode 集无差异。

### 6.2 handle + perform + resume（compat LIR）

**MIR**（取自 `mir-spec.md` §6.3）：

```text
fn#0 main() entry=bb0 regs=6 [main]
  bb0:
    r0 = LOAD_CONST 0   ; 1
    r1 = LOAD_CONST 1   ; 0
    r2 = CALL r</> (r0, r1)
    r3 = LOAD_CONST 0   ; 1
    r4 = LOAD_CONST 1   ; 0
    r5 = CALL r</> (r3, r4)
    r6 = CALL r<+> (r2, r5)
    EFFECT_HANDLE_BEGIN 0, fn#2, ((divide-by-zero, fn#3))
    r7 = CALL r<body-fn> ()
    EFFECT_HANDLE_END 0, r7
    RETURN r7
```

**compat LIR**（折叠后）：

```text
fn#0 main() regs=4 [main]
  0000: LOAD_HOST r0, 1
  0001: LOAD_HOST r1, 0
  0002: CALL r2, r</>, (r0, r1)
  0003: LOAD_HOST r3, 1
  0004: LOAD_HOST r4, 0
  0005: CALL r5, r</>, (r3, r4)
  0006: CALL r6, r<+>, (r2, r5)
  0007: HANDLE r7, fn#2, ((divide-by-zero, fn#3))
  0008: CALL r7, r<body-fn>, ()
  0009: RETURN r7

fn#2 handle-body() regs=2
  0000: ; + (/ 1 0) (/ 1 0) → r0
  0001: RETURN r0

fn#3 handler-divide-by-zero(<ignored>, k) regs=2
  0000: LOAD_HOST r0, 1
  0001: RESUME r0, r<k>, r0
```

要点：

- `EFFECT_HANDLE_BEGIN/END` 折叠为单条 `HANDLE`（END 折叠为 `dst_reg` 的写入）；
- `EFFECT_PERFORM` 折叠为 `PERFORM` + `JUMP resume_target`（resume target 由 `old_to_new` 重映射）；
- `EFFECT_RESUME` 直接 rename 为 `RESUME`；
- 仍使用语言级 `HANDLE` / `RESUME` opcode；dialect 为 `"compat"`。

### 6.3 同一片段在 abstract-machine LIR 中的预期形状（dormant）

**目标 abstract-machine LIR**（若启用 `lower_effects`，**当前未启用**）：

```text
fn#0 main() regs=4 [main]
  frame: function main regs=4 slots=0 ss=(...) saved=()
  0000: LOAD_HOST r0, 1
  0001: LOAD_HOST r1, 0
  0002: CALL r2, r</>, (r0, r1)
  0003: LOAD_HOST r3, 1
  0004: LOAD_HOST r4, 0
  0005: CALL r5, r</>, (r3, r4)
  0006: CALL r6, r<+>, (r2, r5)
  0007: HANDLER_PUSH h0, target=None, parent=-1, specs=((divide-by-zero, fn#3))
  0008: MAKE_FUNCTION r<body>, fn#2
  0009: CALL r7, r<body>, ()
  0010: JUMP <after-region>
  -- dispatch tail (split between HANDLER_POP and after-region):
  0011: EFFECT_DISPATCH r<h-fn>, h0, r<arg>, r<cont>
  0012: CALL r<result>, r<h-fn>, (r<arg>, r<cont>)
  0013: HANDLER_POP h0
  0014: <after-region>
  0015: RETURN r7

handler: h0 effects=[divide-by-zero] target=0011 ss=(...)

fn#3 handler-divide-by-zero(<ignored>, k) regs=2
  0000: LOAD_HOST r0, 1
  0001: CONT_COPY r<k2>, r<k>
  0002: CONT_RESTORE r<k2>, r0, r0
```

要点：

- `HANDLER_PUSH` / `HANDLER_POP` 显式建模 effect marker；
- 续体由 `CONT_CAPTURE` + `EFFECT_UNWIND` 触发（perform 展开）；
- handler 内 resume 用 `CONT_COPY` + `CONT_RESTORE` 组合；
- `LIRProgram.dialect` 标记为 `"abstract-machine"`；
- 此 dialect 不被 `qy/backend/vm/compiler.py:85-88` 接受——LLVM 等后端才能直接消费。

## §7 现状与偏差

### 7.1 固定管线只调 `lower_compat_effects`，不调 `lower_effects`

`qy/passes/lir/lower.py:36-50` 的 `_lower_function` 严格按以下顺序：

```text
linearize_function → lower_compat_effects → peephole → compact_registers
```

`lower_effects`（`qy/passes/lir/effects.py:81`）虽已实现，但**未**接入 driver；`qy/passes/lir/__init__.py:7-10` 只 export `_peephole` 和 `lower_lir`。

后果：最终 LIR 始终是 `compat` dialect，仍保留 `HANDLE` / `PERFORM` / `RESUME`。`abstract-machine only` opcode 永远不出现。

### 7.2 `LIRProgram.dialect` 生产路径恒为 `"compat"`

`LIRProgram.dialect` 默认 `"compat"`（`qy/ir/lir/node.py:191`）。全仓 `dialect="abstract-machine"` 仅在 `tests/test_lir.py:618, 651, 677` 出现。production 代码只读 / 透传该字段，**永不构造** `"abstract-machine"`。

### 7.3 `LOAD_ENV` 未被 lower 成 `SLOT_READ/SS_LOOKUP`

`linearize.py:39-43` 只改写 `LOAD_CONST → LOAD_HOST`；`LOAD_ENV` 与其他 MIR instruction 一起整体 pass-through。当前 LIR 中仍有 `LOAD_ENV`，VM 自行处理 symbol lookup。

与 `docs/lir.md §6.2` 中"静态可解析 symbol 应 lower 成 `SLOT_READ`"的目标差距，需要后续 lowering pass（`symbol_space_layout` / `binding_lowering` 等）补齐。

### 7.4 `CONT_INJECT` 定义但从未 emit

`LIROpcode` 列举 `CONT_INJECT`（`qy/ir/lir/node.py:146`）。`effects.py:267-276` 在 `EFFECT_RESUME` lowering 中仅 emit `CONT_COPY` + `CONT_RESTORE`，**不 emit `CONT_INJECT`**。

spec 把 `CONT_INJECT` 标注为目标 dialect 可用 opcode，但实际 lowering 当前不产生；verifier 不会因为见到它报错。

### 7.5 `HANDLER_FIND` 定义但从未 emit

`HANDLER_FIND` 在 `LIROpcode` 字面集中**未出现**（见 `qy/ir/lir/node.py:79-151`）。此 opcode 在 `docs/lir.md §6.5` 中提到，但当前实现并未把它作为 LIR 一等 opcode 暴露。

### 7.6 `continuous` 标志未传播

`LIRInstruction.continuous` 永远为 `False`：

- `linearize.py:43`、`compat_effects.py` 多处、`peephole.py`、`compact.py` 构造 `LIRInstruction` 时均未传 `continuous=`；
- `lower_effects.py` 也未传。

`docs/ir-design.md §1.2` 描述的连续算子静态不变量当前**未生效**；`_verify_continuous_run` 永不 fire。

### 7.7 多个 MIR opcode 在 LIR 中 pass-through

下列 MIR opcode 在 LIR 阶段保持原 opcode 不变（仅经过 `peephole` / `compact`）：

```text
STORE_LOCAL, MAKE_FUNCTION, MAKE_MACRO, APPLY, CALL, TAIL_CALL,
DEFINE_MODULE, FROM_IMPORT, BUILD_TUPLE,
DEFEFFECT, RAISE_EFFECT,
PARALLEL_GATHER, ALL_GATHER, RACE_FIRST, CACHE_EVAL,
RUNTIME_EVAL, APPEND_RESULT, LOAD_NIL, LOAD_T, MOVE
```

`linearize.py` 不改写它们；`compat_effects.py` 不处理它们；没有 `slot_lowering` / `frame_lowering` pass 把它们映射到抽象机操作。

### 7.8 `LIRFunction.frame_layout` / `symbol_spaces` 的 populate 状态

`compat` dialect 下 `lower_lir` 只构造 `LIRFunction(name, params, register_count, instructions)`；`frame_layout` 与 `symbol_spaces` 默认为空（`None` / `()`）。

`abstract-machine` dialect（`LowerLIRPass` 读取 `PipelineOptions.lir_dialect`）下，`_lower_function_abstract_machine` 现在会填充：

- `frame_layout`：`kind="function"`、`register_count`、保守的 `saved_registers`；
- `handlers`：由 `lower_effects` 产出，含 `handler_target` 与 `parent_handler`；
- `continuations`：由 `lower_effects` 产出，含 `resume_target` 与 `multi_shot`；
- `symbol_spaces`：由 `passes/lir/spaces.py`（`assign_symbol_spaces`）产出，把
  `ENTER_SCOPE` / `EXIT_SCOPE` / `DEFINE_ONCE` 降成
  `SS_ENTER(space_id)` / `SS_LEAVE(space_id)` / `SLOT_COMPLETE(LIRBindingAddr(space, slot), src_reg)`，
  并按线性 scope 栈分配 space id 与 slot index。

因此 L5 / L6 / L7 / L8 / L9 在 abstract-machine dialect 下**不再是空检查**。`SLOT_COMPLETE` 的 operand schema 为 `(LIRBindingAddr, src_reg)`；L9 以函数为单位比较 `(space, slot)` 是否重复 complete。`dump_lir` 在 layout 字段非空时会输出对应段（`pretty.py:39-46`）。

HIR 层 `resolve.spaces` 已实现（见 §7.8 与 `qy/passes/resolve/spaces.py`），产出 `ProgramIR.symbol_spaces`，并由 `MIRProgram` / `LIRProgram` 用共享的 `qy.ir.layout.SymbolSpaceLayout` 携带下沉（`tests/test_resolve_spaces.py` 断言 HIR == MIR == LIR）。仍待推进：MIR 指令 operand 直接携带 binding id/slot；当前 LIR 的 `SLOT_COMPLETE` 地址由 `passes/lir/spaces.py` 从指令流重建，与 HIR slot 一致。

### 7.9 VM 执行 abstract-machine dialect

`qy/backend/vm/compiler.py` 现在接受两种 dialect：`compat` 与 `abstract-machine`。abstract-machine opcode（`SS_*` / `SLOT_COMPLETE` / `HANDLER_*` / `EFFECT_*` / `CONT_*`）已进入 VM opcode 集（`backend/vm/spec/opcode.py`），由 `qy/vm/instance/machine.py` 执行：

- `_Frame` 带显式 `handlers` 栈与 `pending_effect`；
- `EFFECT_UNWIND` 抛 `QyEffectSignal`，持有 `HANDLER_PUSH` 的 frame 在 `CALL` 处捕获并跳到 dispatch block（`EFFECT_DISPATCH` 再把 handler fn / arg / continuation 写进寄存器）；
- `CONT_CAPTURE` 用不可变快照捕获 frame（multi-shot 天然成立，与 compat `_perform` 同构）；`CONT_COPY` 为别名；`CONT_RESTORE` **非终结**，把 resume 结果写回 `dst` 后继续，因此 `(+ (resume k a) (resume k b))` 组合成立；
- `SS_ENTER` / `SS_LEAVE` 对应 `ENTER_SCOPE` / `EXIT_SCOPE`，`SLOT_COMPLETE` 通过 `BytecodeFunction.symbol_spaces` 从 `(space, slot)` 反查符号后 `define_once`。

compat dialect 仍然**拒绝** abstract-machine opcode（L14 结构约束）。`tests/test_abstract_machine_vm.py` 对 `examples/hello.qy` 与全部 validation 样例做 compat/abstract-machine 差分，结果一致。默认执行路径仍是 `compat`。