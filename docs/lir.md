# Qy LIR Design

本文档专门定义 Qy 的 LIR。`docs/ir-design.md` 只描述 HIR / MIR / LIR 的层级边界；本文描述 LIR 自身的数据模型、抽象机器、指令族、lowering 规则、verifier 与迁移路径。

---

# 1. 定位

LIR 是 **Qy abstract machine IR**。

它不是：

- 更扁平的 MIR；
- bytecode 的文本版；
- register VM 当前 opcode 的同构镜像；
- Python runtime object 的包装层。

它是 MIR 与 bytecode / LLVM / libqy VM 之间的低层语义机器层，负责把 Qy 语言中仍然隐含的执行机制全部显式化：

- virtual stack；
- function frame；
- continuation frame；
- handler frame / effect marker；
- symbol-space-chain transition；
- binding slot read / complete / pending；
- lookup operation；
- call ABI；
- host capability ABI；
- task / join / race frame；
- relocation / layout / fixup；
- debug / trace map。

一句话：

```text
MIR 描述程序控制流；
LIR 描述 Qy 抽象机器如何执行这些控制流。
```

---

# 2. 输入与输出

## 2.1 输入

LIR lowering 的输入是 verified MIR。

MIR 必须已经给出：

- CFG；
- virtual register；
- explicit branch / jump / return / tail-call；
- effect region / perform edge / resume edge；
- binding ref；
- module / fold operation；
- source debug metadata。

LIR lowering 不应重新访问：

- raw AST；
- HIR tree；
- macro namespace；
- runtime `Environment`；
- Python host object layout。

## 2.2 输出

LIR 输出是 verified Qy abstract-machine program：

- linearized function body；
- selected low-level instruction；
- frame layout；
- symbol-space layout；
- continuation layout；
- handler layout；
- slot layout；
- relocation table；
- debug table；
- constant / function / host reference table。

`LIR -> bytecode` 只能做：

- encode；
- pack；
- relocate；
- attach tables。

如果 bytecode compiler 仍然需要理解 `handle`、`perform`、`resume`、`define`、`module`、`tail call` 的语言语义，说明 LIR 尚未完成。

---

# 3. 抽象机器状态

LIR 面向的 Qy abstract machine 至少包含以下状态：

```text
MachineState:
  current_frame
  virtual_stack
  current_ss_chain
  current_handler
  pending_continuations
  task_set
  result_register
```

## 3.1 Virtual Stack

virtual stack 是 Qy 求值的主执行结构。它不是 Python call stack。

每个 frame 至少携带：

- frame id；
- function id；
- program counter；
- physical register segment；
- local slot segment；
- current symbol-space-chain；
- parent frame；
- active handler marker；
- debug span；
- tail-call policy。

```text
Frame:
  kind: function | continuation | handler | task
  pc
  registers
  locals
  ss_chain
  parent
  handler
  debug
```

## 3.2 Symbol-Space-Chain

LIR 必须把 symbol-space-chain 显式化。

`symbol-space-chain` 不是 Python `Environment`，也不是 hash map 的隐式 parent 指针。它是可进入、离开、复制、恢复的运行时结构。

```text
SymbolSpace:
  id
  parent
  lookup_index: SymbolId -> SlotIndex
  slots: BindingSlot[]
  metadata: SymbolMeta[]
```

```text
BindingSlot:
  addr: (space-id, slot-index)
  state: declared | pending | completed | poisoned
  value: Value | empty
```

metadata 是冷数据：

- declaration span；
- export flag；
- operator signature；
- hygiene / capture info；
- debug info。

value 是热数据。metadata 不应污染热路径。

## 3.3 Continuation

continuation 是从 perform 点到 handler marker 之间的 delimited virtual stack segment。

Qy 默认语义应支持 multi-shot，因此 LIR 需要显式区分：

- capture；
- copy；
- restore；
- inject resume value；
- jump to resume target。

```text
ContinuationFrame:
  id
  resume_target
  saved_frames
  saved_registers
  saved_ss_chain
  inject_register
  multi_shot
```

multi-shot 不代表深拷贝所有 runtime object。它复制控制状态与 ss-chain 状态；host reference、array、hash-map 等对象是否共享，由 value 自身的 copy / clone / identity 协议决定。

## 3.4 Handler

handler 是 virtual stack 上的 effect marker。

```text
HandlerFrame:
  id
  effect_set
  handler_target
  parent_handler
  handler_ss_chain
  resume_policy
```

`perform` 找 handler 走 dynamic virtual stack / handler chain；symbol lookup 走 ss-chain。两者不能混为一条链。

---

# 4. 核心 Operand

LIR operand 不应使用随意 Python object。

建议的 operand family：

- `Reg`: physical register or compact frame register；
- `ConstRef`: constant table index；
- `FunctionRef`: function table index；
- `SymbolId`: interned syntax symbol identity；
- `SpaceId`: symbol-space layout id；
- `SlotAddr`: `(space-id, slot-index)`；
- `FrameId`: frame layout id；
- `ContinuationId`: continuation layout id；
- `HandlerId`: handler layout id；
- `LabelRef`: relocation label；
- `HostAbiRef`: host capability ABI declaration；
- `DebugRef`: source map / trace map id。

禁止：

- raw AST tuple；
- HIR node；
- MIR block object；
- runtime `Environment`；
- arbitrary Python object；
- source-level symbol name lookup。

---

# 5. Program Model

目标 LIR program 形状：

```text
LIRProgram:
  version
  functions
  constants
  symbol_spaces
  host_abi
  debug
  diagnostics
```

```text
LIRFunction:
  id
  name
  params
  frame_layout
  instruction_stream
  relocations
  continuations
  handlers
  debug_map
```

```text
LIRInstruction:
  opcode
  operands
  span/debug
```

LIR 可以在 pass 内部使用 label / block-like 结构，但 verified final LIR 应该已经完成 layout，或者至少只留下 bytecode compiler 能机械 relocate 的 label/ref。

---

# 6. 指令族

下面是目标 vocabulary。名字可以在实现时调整，但职责边界不能变。

## 6.1 Value / Register

- `LOAD_CONST dst, const-ref`
- `LOAD_NIL dst`
- `LOAD_T dst`
- `MOVE dst, src`
- `PHI_MOVE dst, src...`（若 MIR 未来采用 block parameter，可在 LIR 消除）
- `BUILD_CHAIN dst, head, tail`
- `BUILD_ARRAY dst, element-type, values...`
- `BUILD_HASH_MAP dst, entries...`

`LOAD_HOST` 不应是目标 LIR 指令。host object 必须通过 host reference constant 或 host ABI ref 进入。

## 6.2 Symbol-Space / Slot

- `SS_ENTER space-id`
- `SS_LEAVE space-id`
- `SS_COPY dst, ss-chain`
- `SS_RESTORE ss-chain`
- `SS_LOOKUP dst, symbol-id, ss-chain`
- `SLOT_READ dst, slot-addr`
- `SLOT_COMPLETE slot-addr, value-reg`
- `SLOT_STATE dst, slot-addr`
- `SLOT_PENDING_EFFORT dst, slot-addr`
- `FOLD_EXPORTS dst-space, export-view`

规则：

- 静态可解析 symbol 应 lower 成 `SLOT_READ`；
- 只有 `eval`、dynamic import、host bridge 等场景保留 `SS_LOOKUP`；
- `define` 只提升 slot 分配，不提升 RHS 求值；
- `SLOT_COMPLETE` 是 once-complete，重复 complete 是 verifier / runtime error；
- 读取 pending slot 必须显式走 `SLOT_PENDING_EFFORT` 或 effect edge。

## 6.3 Frame / Call

- `FRAME_ENTER frame-layout`
- `FRAME_LEAVE frame-layout`
- `CALL dst, function-ref/reg, args...`
- `TAIL_CALL function-ref/reg, args...`
- `APPLY dst, function-reg, args-reg`
- `RETURN value-reg`
- `CALL_HOST dst, host-abi-ref, args...`

规则：

- tail call 是 frame operation，不是普通 call 后接 return；
- host call ABI 必须在 LIR 明确，不允许 VM 从 Python callable 猜测；
- closure 捕获应指向 binding slot / ss-chain ref，不捕获 Python `Environment`。

## 6.4 Control

- `LABEL label`
- `JUMP label`
- `BR_NIL cond-reg, true-label, false-label`
- `BR_EQ a, b, true-label, false-label`
- `SWITCH value-reg, table, default-label`
- `UNREACHABLE`

规则：

- `cond` 的核心 false 只认 `nil`；
- `truthy` 是普通算子，不改变 `BR_NIL` 的语义；
- final LIR 可保留 relocatable label，但 bytecode compiler 只能机械 fixup。

## 6.5 Handler / Effect / Continuation

目标 LIR 不允许保留语言级：

- `HANDLE`
- `PERFORM`
- `RESUME`

它们必须 lower 为：

- `HANDLER_PUSH handler-layout`
- `HANDLER_POP handler-id`
- `HANDLER_FIND dst, effect-ref`
- `CONT_CAPTURE dst, resume-label, live-regs, ss-chain`
- `CONT_COPY dst, cont-reg`
- `CONT_RESTORE cont-reg`
- `CONT_INJECT cont-reg, value-reg`
- `EFFECT_UNWIND handler-reg, effect-ref, arg-reg, cont-reg`
- `EFFECT_DISPATCH handler-reg, arg-reg, cont-reg`

### 6.5.1 perform lowering

HIR:

```lisp
(perform effect arg)
```

MIR:

```text
perform edge(effect, arg, resume-block)
```

LIR 概念序列：

```text
CONT_CAPTURE   r_k, L_resume, live-regs, current-ss-chain
HANDLER_FIND   r_h, effect
EFFECT_UNWIND  r_h, effect, r_arg, r_k
EFFECT_DISPATCH r_h, r_arg, r_k
JUMP           L_after_dispatch

LABEL L_resume
CONT_TAKE_VALUE r_result
```

具体是否需要 `CONT_TAKE_VALUE` 可以由 ABI 决定；核心要求是 resume value 注入必须显式。

## 6.5.2 resume lowering

HIR:

```lisp
(resume k value)
```

LIR 概念序列：

```text
CONT_COPY      r_k2, r_k
CONT_INJECT    r_k2, r_value
CONT_RESTORE   r_k2
JUMP           r_k2.resume_target
```

multi-shot 默认通过 `CONT_COPY` 表达。one-shot 优化可以把 `CONT_COPY` 改成 move，但不得改变语言语义。

## 6.6 Parallel / All / Race

- `TASK_FORK dst-task, entry, captured-ss-chain`
- `TASK_JOIN_ALL dst, task-list`
- `TASK_RACE dst, task-list`
- `TASK_CANCEL task`
- `JOIN_FRAME_CREATE dst, policy`
- `JOIN_FRAME_RESUME join, value`

规则：

- `parallel` 表示允许并行，不要求并行；
- `all` 是 barrier continuation；
- `race` 是 first-resume-wins；
- task frame 必须携带 ss-chain；
- effect 在 task 内触发时，continuation segment 属于该 task 的 virtual stack。

## 6.7 Module / Fold

- `MODULE_CREATE dst-space, module-id`
- `EXPORT_BINDING module-space, slot-addr`
- `EXPORT_VIEW_CREATE dst, module-space, exports`
- `FOLD_EXPORTS dst-space, export-view`

规则：

- `from` 是 selective fold；
- fold 后 binding 属于目标 symbol-space 的 local membership；
- import alias 冲突按 define-once 处理；
- macro export 与 runtime export 可以使用不同 namespace，但 fold primitive 应统一。

---

# 7. define 与 pending binding

Qy 的 `define` 语义：

```text
compile/analyze:
  scan direct definitions
  allocate binding slots
  resolve symbol refs to slot addresses

runtime:
  execute body in source order
  execute define RHS in source order
  complete slot once
```

示例：

```lisp
(pipeline
  (echo x)
  (define x (op ...)))
```

LIR 概念形状：

```text
; layout phase
space s0:
  slot0 = x, state=declared

; runtime order preserved
SLOT_READ            r_x, s0.slot0
SLOT_PENDING_EFFORT  r_x, s0.slot0   ; if slot is not completed
CALL                 r0, echo, r_x

CALL                 r_v, op
SLOT_COMPLETE        s0.slot0, r_v
```

这说明：

- `x` 是 resolved；
- `x` 不是 unresolved symbol；
- RHS 没有提前求值；
- 读取 pending binding 是 effort，不是 Python exception 的偶然行为。

---

# 8. LIR Pass Pipeline

建议 pass 顺序：

1. **Selection**
   - MIR opcode / terminator 选择成 LIR pseudo instruction。

2. **Symbol-Space Layout**
   - 分配 `SymbolSpaceLayout`；
   - 分配 `BindingSlot`；
   - 降低 resolved symbol 为 `SlotAddr`。

3. **Frame Layout**
   - 分配 register segment；
   - 分配 local slot segment；
   - 定义 function frame ABI。

4. **Effect Lowering**
   - 消除语言级 `handle` / `perform` / `resume`；
   - 生成 handler frame、continuation frame、effect unwind / dispatch。

5. **SS-Chain Lowering**
   - 插入 `SS_ENTER` / `SS_LEAVE` / `SS_COPY` / `SS_RESTORE`。

6. **Call ABI Lowering**
   - 降低 function call、tail call、host call、apply。

7. **Parallel Lowering**
   - 生成 task frame、join frame、race winner continuation。

8. **Block Layout**
   - linearize；
   - rerank hot/cold blocks；
   - 生成 relocation。

9. **Register Allocation / Compaction**
   - virtual register 到 physical register / frame slot。

10. **Peephole**
   - 删除 redundant move；
   - 合并 enter/leave；
   - 简化 jump-to-next；
   - 常量专用 load。

11. **Debug Injection**
   - span map；
   - trace hook；
   - stack map；
   - continuation map。

12. **Verification**
   - 输出 verified LIR。

---

# 9. Verifier

LIR verifier 至少检查：

## 9.1 结构

- function id 唯一；
- main function 合法；
- instruction operand kind 合法；
- label / relocation target 合法；
- register / frame slot 不越界；
- no pseudo instruction；
- no HIR / MIR object payload；
- no runtime `Environment`。

## 9.2 Symbol-Space / Slot

- `SlotAddr` 指向存在的 symbol-space；
- slot index 合法；
- `SLOT_COMPLETE` 对同一 slot 最多一次；
- `SLOT_READ` pending path 明确；
- fold 冲突规则可检查；
- metadata index 合法；
- static symbol ref 不退回 source-level lookup。

## 9.3 Frame / Call

- `FRAME_ENTER` / `FRAME_LEAVE` 平衡；
- tail call 不增长 frame；
- call ABI 参数数量与声明一致；
- host ABI ref 合法；
- closure 捕获不含 Python env。

## 9.4 Effect / Continuation

- 无语言级 `HANDLE` / `PERFORM` / `RESUME`；
- handler push/pop 平衡；
- handler target 合法；
- perform edge 已 lower 成 unwind / dispatch；
- continuation capture live-reg map 完整；
- continuation restore 目标合法；
- resume value injection register 合法；
- multi-shot continuation 使用 copy 或等价语义；
- ss-chain restore 与 continuation frame 匹配。

## 9.5 Parallel

- task frame 携带 ss-chain；
- `all` join 必须有 barrier；
- `race` 必须有 winner continuation；
- loser cancellation policy 明确；
- effect continuation 不跨 task 非法逃逸。

---

# 10. 与 Bytecode / LLVM / libqy 的关系

## 10.1 Bytecode

bytecode 是 register VM 的最终执行输入。

bytecode compiler 只允许：

- encode LIR opcode；
- pack operands；
- apply relocation；
- attach function/constant/debug tables。

bytecode 不允许：

- 重新解析 binding；
- 再次决定 handler lookup；
- 再次构造 continuation layout；
- 根据 Python callable 猜 host ABI；
- 把 pending binding 变成普通 unresolved error。

## 10.2 LLVM

LLVM backend 应消费 verified LIR，而不是 MIR 或 HIR。

LLVM codegen 应看到的是：

- value layout；
- frame layout；
- slot layout；
- continuation layout；
- handler layout；
- ss-chain operation；
- ABI-lowered calls。

LLVM backend 不应看到：

- source-level `perform`；
- source-level `handle`；
- source-level `resume`；
- Python `_EffectFrame`；
- Python `Environment`。

## 10.3 libqy VM

若未来存在 libqy VM，它也应以 LIR/bytecode 的抽象机器模型为输入，而不是重新实现一套语言解释器。

---

# 11. Compat LIR 与目标 LIR

当前实现可以保留迁移期 `compat LIR`：

- 与现有 bytecode opcode 部分同构；
- 可暂时保留 `PERFORM` / `HANDLE` / `RESUME`；
- 用于保持现有测试和 register VM 路径可运行。

但 `compat LIR` 是删除对象，不是目标模型。

目标 `abstract-machine LIR`：

- 禁止语言级 effect opcode；
- 禁止 Python object payload；
- 显式建模 symbol-space / slot；
- 显式建模 continuation / handler；
- bytecode compiler 只能编码；
- LLVM/backend 可以直接消费。

迁移规则：

- 新语义只能进入目标 LIR；
- 旧 compat opcode 只能减少；
- 每移除一类 compat opcode，必须增加对应 target LIR verifier；
- CLI `qy lir` 应能标明当前 dump 属于 compat 还是 abstract-machine。

---

# 12. 最小落地顺序

## Step 1. 数据模型

- `LIRProgram`
- `LIRFunction`
- `LIRInstruction`
- `LIRFrameLayout`
- `LIRSymbolSpaceLayout`
- `LIRBindingSlot`
- `LIRContinuationLayout`
- `LIRHandlerLayout`
- `LIRRelocation`
- `LIRDebugMap`

## Step 2. Verifier

先做只读 verifier，不改执行：

- 检查 operand kind；
- 检查 slot addr；
- 检查 no language-level effect opcode；
- 检查 frame/handler/continuation layout；
- 检查 no Python payload。

## Step 3. Dump

CLI 能展示：

- frame layout；
- ss-chain；
- slot table；
- continuation table；
- handler table；
- instruction stream；
- relocation；
- debug map。

## Step 4. Symbol-Space Lowering

先迁移 resolved symbol：

```text
LOAD_ENV symbol
  -> SLOT_READ slot-addr
```

`define`：

```text
DEFINE_ONCE symbol, value
  -> SLOT_COMPLETE slot-addr, value
```

pending read：

```text
SLOT_READ pending
  -> SLOT_PENDING_EFFORT
```

## Step 5. Effect Lowering

迁移：

- `HANDLE` -> `HANDLER_PUSH` / `HANDLER_POP`
- `PERFORM` -> `CONT_CAPTURE` / `HANDLER_FIND` / `EFFECT_UNWIND` / `EFFECT_DISPATCH`
- `RESUME` -> `CONT_COPY` / `CONT_INJECT` / `CONT_RESTORE` / `JUMP`

## Step 6. Bytecode Encoding

新增 bytecode encoding path：

```text
abstract-machine LIR -> abstract-machine bytecode -> register VM
```

旧 `compat LIR -> old bytecode` 保留到测试迁完。

## Step 7. 删除 Compat

当以下完成后删除 compat：

- core examples 通过；
- qytest 通过；
- effect + continuation tests 通过；
- parallel/all/race tests 通过；
- module/fold tests 通过；
- CLI dumps 稳定；
- bytecode compiler 不再有 semantic lowering。

---

# 13. 完成标准

LIR 完成时，应满足：

- `qy lir` 不再展示语言级 `HANDLE` / `PERFORM` / `RESUME`；
- `qy lir` 能展示 frame、slot、ss-chain、handler、continuation；
- bytecode compiler 只编码；
- register VM 不再靠 Python `_EffectFrame` 临时拼语义；
- pending binding 有明确 effort path；
- `define` 前向引用可静态解析但不提前求值；
- tail call 与 effect boundary 可由 virtual stack 模型解释；
- LLVM/backend 可从 verified LIR 生成代码，不需要读 HIR/MIR；
- analyzer / LSP 不依赖 LIR，但 LIR dump 能用于调试低层执行。

