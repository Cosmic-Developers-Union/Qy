# Qy MIR 语言规范

## §0 目的与受众

本文档是 Qy MIR（控制流 + 虚拟寄存器 IR）的**正式语言规范**，是 MIR 形态的规范真源。它面向：

- 为 pipeline 的 MIR 阶段编写测试的工程师（可对照此文档断言 opcode 序列）；
- 阅读 `qy/passes/mir/normalize.py` 的贡献者（每条 HIR→MIR 规则在 §5 有对应条目）；
- 维护 pass scheduler / dump CLI 的工程师。

本文档规定：

- MIR 的 EBNF 文法；
- 每个 opcode 的 operand 含义与不变量；
- MIR verifier 应当检查的不变量；
- 从 HIR 到 MIR 的 lowering 映射。

本文档**不**规定：

- MIR→LIR 的 lowering（见 `docs/lir-spec.md`）；
- 高层边界与设计意图（见 `docs/ir-design.md` §3）；
- VM 物理寄存器与 layout（见 `docs/lir-spec.md`）。

实现真源：`qy/ir/mir/node.py`、`qy/passes/mir/lower_pass.py`、`qy/passes/mir/normalize.py`、`qy/passes/mir/validate.py`、`qy/ir/mir/__init__.py`。

## §1 层定位

MIR 是**控制流 + 虚拟寄存器 IR**。它在 HIR 之上构造。

它**回答**：

- 程序按照什么控制流执行？
- 哪些值流入哪些后续计算？
- 哪些分支、尾调用、effect、join 是显式控制边？

它**不**回答：

- 最终物理寄存器是多少；
- bytecode 如何编码；
- host call ABI 是什么；
- source spelling 是什么。

边界与设计意图详见 `docs/ir-design.md` §3；MIR→LIR 的 lowering 详见 `docs/lir-spec.md` §5。

## §2 EBNF 文法

### Legend

- `xxx?` 零或一次
- `xxx*` 零或多次
- `xxx+` 一或多次
- **粗体**：保留字 / 字面 token
- `Symbol`、`SourceSpan`、`Diagnostic`：复用类型（见 §2.1）
- 寄存器与 block id 是 32 位无符号整数；constant pool index 同

### 2.1 复用类型

| 类型 | 来源 | 说明 |
| --- | --- | --- |
| `Symbol` | `qy.frontend.reader` | interned identifier |
| `SourceSpan` | `qy.frontend.reader` / `qy.errors` | source 位置 |
| `Diagnostic` | `qy.diag` | 编译期诊断 |

### 2.2 顶层

```text
MIRProgram      := "MIRProgram" "{"
                      "functions"   ":" MIRFunction+ ","
                      "constants"   ":" MIRConstantPool ","
                      "main"        ":" int "= 0" ","
                      "diagnostics" ":" Diagnostic* "}"

MIRFunction     := "MIRFunction" "{"
                      "name"           ":" Symbol ","
                      "params"         ":" Symbol+ ","
                      "register_count" ":" int ","
                      "blocks"         ":" MIRBlock+ ","
                      "entry"          ":" MIRBlockId "= 0" "}"

MIRBlock        := "MIRBlock" "{"
                      "id"           ":" MIRBlockId ","
                      "instructions" ":" MIRInstruction* ","
                      "terminator"   ":" MIRTerminator "}"

MIRInstruction  := "MIRInstruction" "{"
                      "opcode"     ":" MIROpcode ","
                      "operands"   ":" Any* ","
                      "span"       ":" SourceSpan? ","
                      "continuous" ":" bool "= false" "}"

MIRTerminator   := "MIRTerminator" "{"
                      "opcode"   ":" MIRTerminatorOpcode ","
                      "operands" ":" Any* ","
                      "span"     ":" SourceSpan? "}"

MIRConstantPool := "MIRConstantPool" "{" "values" ":" Any* "}"
```

派生属性：`MIRProgram.ok` 当且仅当 `diagnostics` 中无 `severity == "error"`。

### 2.3 opcode 字面集

```text
MIROpcode            := "APPEND_RESULT" | "ALL_GATHER" | "APPLY" | "BUILD_TUPLE"
                      | "CACHE_EVAL" | "CALL" | "DEFEFFECT" | "DEFINE_MODULE"
                      | "DEFINE_ONCE" | "EFFECT_HANDLE_BEGIN" | "EFFECT_HANDLE_END"
                      | "EFFECT_RESUME" | "ENTER_SCOPE" | "EXIT_SCOPE"
                      | "FROM_IMPORT" | "LOAD_CONST" | "LOAD_HOST" | "LOAD_ENV"
                      | "MAKE_FUNCTION" | "MAKE_MACRO" | "MOVE" | "PARALLEL_GATHER"
                      | "RACE_FIRST" | "RUNTIME_EVAL" | "STORE_LOCAL"

MIRTerminatorOpcode  := "BRANCH" | "EFFECT_PERFORM" | "JUMP" | "RAISE_EFFECT"
                      | "RETURN" | "TAIL_CALL"
```

opcode 字面集见 `qy/ir/mir/node.py:34-69`。每条 opcode 的语义在 §3 中详述。

### 2.4 leaf 类型

```text
MIRRegister      := int         "≥ 0, < register_count"
MIRBlockId       := int         "≥ 0, < len(blocks)"
MIRFunctionIndex := int         "≥ 0, < len(functions)"
```

`MIRConstantPool.intern(value)` 把对象加入池并返回新 index；同值可出现在多个 index（identity 保留）。

## §3 opcode 目录

按家族分节。每条 opcode 给出：**语法形状**（EBNF operand 模板）、**字段语义**、**不变量**。

### 3.1 Value / Constant

#### LOAD_CONST

```text
LOAD_CONST dst: MIRRegister, pool_idx: int
```

| 字段 | 含义 |
| --- | --- |
| `dst` | 目标寄存器 |
| `pool_idx` | `MIRConstantPool` 中的 index |

不变量：`pool_idx ∈ [0, len(constants.values))`。

#### LOAD_HOST

```text
LOAD_HOST dst: MIRRegister, value: Any
```

| 字段 | 含义 |
| --- | --- |
| `dst` | 目标寄存器 |
| `value` | 宿主对象；当前实现直接嵌入（迁移期；见 §7） |

> 当前实现不通过 `MIRConstantPool` 注入 host value；这是与"目标 MIR 不携带宿主偶然表示"的差距（事实见 §7）。

#### LOAD_NIL / LOAD_T / MOVE

```text
LOAD_NIL dst: MIRRegister
LOAD_T   dst: MIRRegister
MOVE     dst: MIRRegister, src: MIRRegister
```

`LOAD_NIL` / `LOAD_T` 是 Qy `nil` / `t` 的字面加载。MOVE 是寄存器间复制。

### 3.2 Storage / Binding

#### STORE_LOCAL

```text
STORE_LOCAL symbol: Symbol, src: MIRRegister
```

把 `src` 存入当前 scope 的本地 binding `symbol`。定义于当前 `ENTER_SCOPE`/`EXIT_SCOPE` 区间。

#### DEFINE_ONCE

```text
DEFINE_ONCE name: Symbol, src: MIRRegister
```

在当前空间内把 `name` 一次性绑定到 `src`。重复 `DEFINE_ONCE(name)` 是 verifier / runtime error。

不变量：name 必须尚未在该空间绑定（define-once）。

### 3.3 Function construction

#### MAKE_FUNCTION

```text
MAKE_FUNCTION dst: MIRRegister, fn_idx: MIRFunctionIndex
```

构造一个运行时可调用的函数值（指向 `functions[fn_idx]`）。

#### MAKE_MACRO

```text
MAKE_MACRO dst: MIRRegister, name: Symbol, params: tuple[Symbol, ...], raw_body: tuple[Any, ...]
```

构造一个 compile-time macro 对象；不在 runtime 调用。

#### APPLY

```text
APPLY dst: MIRRegister, fn_reg: MIRRegister, args_reg: MIRRegister
```

把 `args_reg` 中的运行时 chain 拆为多参数，调用 `fn_reg`。

### 3.4 Scope

#### ENTER_SCOPE / EXIT_SCOPE

```text
ENTER_SCOPE
EXIT_SCOPE
```

无 operand。区间内允许 `STORE_LOCAL`。`EXIT_SCOPE` 必须对应之前未配对的 `ENTER_SCOPE`。

不变量：每个函数入口存在 `ENTER_SCOPE`；每对 `ENTER_SCOPE`/`EXIT_SCOPE` 必须正确嵌套。

### 3.5 Effect

#### DEFEFFECT

```text
DEFEFFECT name: Symbol, resumable: bool
```

注册 effect 声明到 MIR lowering 的 `effect_table`。无 `dst`；声明无返回值。

#### EFFECT_HANDLE_BEGIN

```text
EFFECT_HANDLE_BEGIN handle_id: int, body_fn_idx: MIRFunctionIndex, specs: tuple[EffectSpec, ...]
```

标记 effect handler region 起点；operand 描述 body 函数与每个 effect 的 handler 函数。

#### EFFECT_HANDLE_END

```text
EFFECT_HANDLE_END handle_id: int, dst_reg: MIRRegister
```

标记 effect handler region 终点；`dst_reg` 接收 body 结果。

不变量：每个 `EFFECT_HANDLE_BEGIN(handle_id)` 必须有匹配的 `EFFECT_HANDLE_END(handle_id)`；区间内允许 `EFFECT_PERFORM`。

#### EFFECT_RESUME（指令）

```text
EFFECT_RESUME dst: MIRRegister, cont_reg: MIRRegister, value_reg: MIRRegister
```

非尾位置 resume。把 `value_reg` 注入 continuation 并跳到 resume target。

#### EFFECT_PERFORM（terminator）

```text
EFFECT_PERFORM dst: MIRRegister, effect: Symbol, arg_reg: MIRRegister,
                  resume_block: MIRBlockId, resumable: bool
```

触发 effect：捕获当前求值上下文，把控制权交给最近的匹配 handler。`resume_block` 是 effect resume 后的 fall-through 目标。

不变量：`resumable=True` 时 `resume_block` 必须可达。

#### RAISE_EFFECT（terminator）

```text
RAISE_EFFECT effect: Symbol, arg_reg: MIRRegister, resumable: bool
```

发起不可恢复 effect；不返回。当 `resumable=False` 时使用。

### 3.6 Concurrency

#### PARALLEL_GATHER / ALL_GATHER / RACE_FIRST

```text
PARALLEL_GATHER dst: MIRRegister, fn_indices: MIRFunctionIndex+
ALL_GATHER       dst: MIRRegister, fn_indices: MIRFunctionIndex+
RACE_FIRST       dst: MIRRegister, fn_indices: MIRFunctionIndex+
```

| opcode | 语义 |
| --- | --- |
| `PARALLEL_GATHER` | 标记一组 thunk 求值顺序无关；VM 可并行 |
| `ALL_GATHER` | barrier continuation；所有 thunk 完成后父级恢复 |
| `RACE_FIRST` | first-resume-wins；最先恢复的 thunk 胜出 |

不变量：`fn_indices` 至少 1 个；每个 `fn_indices[i]` 指向独立 thunk 函数。

#### CACHE_EVAL

```text
CACHE_EVAL dst: MIRRegister, cache_key: Any, thunk_fn_idx: MIRFunctionIndex
```

按 `cache_key` 缓存 thunk 的求值结果。

### 3.7 Module

#### DEFINE_MODULE

```text
DEFINE_MODULE dst: MIRRegister, name: Symbol, body_fn_idx: MIRFunctionIndex, exports: tuple[Symbol, ...]
```

构造 module 对象；`exports` 给出 export view。

#### FROM_IMPORT

```text
FROM_IMPORT module: Symbol, specs: tuple[ImportSpec, ...]
```

无 `dst`；按 `specs` 把目标 module 的 export view fold 到当前 symbol-space。

### 3.8 Meta

#### RUNTIME_EVAL

```text
RUNTIME_EVAL dst: MIRRegister, inner_reg: MIRRegister
```

把 `inner_reg` 中承载的 syntax datum 在运行时求值。

### 3.9 Data / Result

#### BUILD_TUPLE

```text
BUILD_TUPLE dst: MIRRegister, regs: MIRRegister+
```

把多个寄存器值组装为运行时 tuple。

#### APPEND_RESULT

```text
APPEND_RESULT src: MIRRegister
```

把顶层表达式结果附加到 main 函数的 result list；仅 main 入口使用。

### 3.10 Terminator

#### JUMP

```text
JUMP target: MIRBlockId
```

无条件跳转到 `target`。

#### BRANCH

```text
BRANCH cond: MIRRegister, true_block: MIRBlockId, false_block: MIRBlockId
```

根据 `cond` 选择下一 block。`cond` 的"假"等于 Qy `nil`；"真"为其他值。

#### RETURN

```text
RETURN src: MIRRegister? = None
```

函数返回；`src` 为结果寄存器，`None` 表示无返回值。

#### TAIL_CALL

```text
TAIL_CALL fn: MIRRegister, args: tuple[MIRRegister, ...]
```

尾位置调用；不增长 call stack。

不变量：仅在 terminator 位置合法。

## §4 Verifier 规则

实现：`qy/ir/mir/__init__.py`（`verify_mir` 等），由 `qy/passes/mir/validate.py` 调用。

| 编号 | 不变量 |
| --- | --- |
| M1 | `main ∈ [0, len(functions))` |
| M2 | 每个 `MIRBlock.id` 唯一 |
| M3 | `MIRFunction.entry ∈ [0, len(blocks))` |
| M4 | 每个 `MIRBlock` 恰有一个 `MIRTerminator` |
| M5 | `BRANCH` 的 `true_block` / `false_block` 均在 `functions[main].blocks` 范围内 |
| M6 | `JUMP` 的 `target` 在 `functions[main].blocks` 范围内 |
| M7 | `CALL` / `TAIL_CALL` 等引用的寄存器 < `register_count` |
| M8 | `TAIL_CALL` 仅在 `MIRTerminator` 位置出现 |
| M9 | `EFFECT_HANDLE_BEGIN` / `EFFECT_HANDLE_END(handle_id)` 配对；不允许跨函数泄漏 |
| M10 | `ENTER_SCOPE` / `EXIT_SCOPE` 正确嵌套；不跨函数泄漏 |
| M11 | 死 block（无 predecessor 且非 entry）若不影响结果可保留，但需在 dump 中标注 |
| M12 | `_verify_continuous_run`（`__init__.py:464-513`）：`continuous=True` 指令不得是 break-point opcode；同一 block 内不得与 break-point opcode 相邻 |

`break-point opcode` 集合见 `_CONTINUOUS_BREAK_OPCODES`（`qy/ir/mir/__init__.py:445-461`），包含 scope / handler / effect 切换与 join opcode。

## §5 HIR → MIR 映射

**实现真源**：`qy/passes/mir/normalize.py`，dispatch 在 `_FunctionLowerer.lower_expr`（`normalize.py:126-206`），通过 `isinstance` 链分派。

### 5.1 映射表

| HIR 节点 | MIR 序列 | 实现位置 |
| --- | --- | --- |
| `LiteralExpr` | `LOAD_CONST dst, interned_idx`（通过 `emit_load_const`） | `normalize.py:127-130` |
| `QuoteExpr` | `LOAD_CONST dst, _quote_data(form)` | `normalize.py:131-134` |
| `SymbolRefExpr` / `UnresolvedSymbolExpr` | `LOAD_ENV dst, symbol` | `normalize.py:135-138` |
| `DefunExpr` | 嵌套 `lower_function(body)` + `MAKE_FUNCTION dst, fn_idx` + `DEFINE_ONCE name, dst` | `normalize.py:139-148` |
| `LambdaExpr` | 嵌套 `lower_function` + `MAKE_FUNCTION dst, fn_idx`（无 `DEFINE_ONCE`） | `normalize.py:149-157` |
| `MacroExpr` | `MAKE_MACRO dst, name, params, raw_body` + `DEFINE_ONCE name, dst` | `normalize.py:158-169` |
| `LetExpr` | `ENTER_SCOPE`；每个 binding lower + `STORE_LOCAL name, val_reg`；body；`EXIT_SCOPE` | `lower_let` `normalize.py:208-219` |
| `CondExpr` | 每个 clause：lower cond + `BRANCH cond, then_id, next_id`；then-result lowered；末 clause 失败时 `LOAD_CONST None` fall-through | `lower_cond` `normalize.py:221-264` |
| `CallExpr`（非尾） | lower operator + args + `CALL dst, op_reg, arg_reg*` | `lower_call` `normalize.py:266-285` |
| `CallExpr`（`tail_position=True`） | terminator `TAIL_CALL op_reg, arg_reg*` | `normalize.py:275-282` |
| `AssertExpr` | lower cond + `BRANCH cond, pass_id, fail_id`；fail → `LOAD_CONST "assertion failed"`（如无 message）+ `RAISE_EFFECT assert-failed, msg, False`；pass → `MOVE dst, cond_reg` | `lower_assert` `normalize.py:287-330` |
| `RuntimeEvalExpr` | lower inner + `RUNTIME_EVAL dst, inner_reg` | `lower_runtime_eval` `normalize.py:332-338` |
| `ModuleExpr` | 嵌套 `lower_function(body)` + `DEFINE_MODULE dst, name, fn_idx, exports` | `lower_module` `normalize.py:340-355` |
| `FromImportExpr` | `FROM_IMPORT module, specs`（无 `dst`） | `lower_from_import` `normalize.py:357-359` |
| `DefeffectExpr` | 注册到 `_MIRLowerer.effect_table` + `DEFEFFECT name, resumable`（无 `dst`） | `lower_defeffect` `normalize.py:361-364` |
| `PerformExpr` | lower arg + 分配 `resume_block_id` + terminator `EFFECT_PERFORM dst, effect, arg_reg, resume_block_id, resumable`；fall-through block 承载 resume 续体 | `lower_perform` `normalize.py:366-383` |
| `HandleExpr` | 嵌套 `lower_function` for body；每个 `EffectHandler` 嵌套函数；分配 `handle_id`；`EFFECT_HANDLE_BEGIN handle_id, body_fn_idx, specs` + `EFFECT_HANDLE_END handle_id, dst_reg` | `lower_handle` `normalize.py:385-414` |
| `ResumeExpr` | lower cont + value + `EFFECT_RESUME dst, cont_reg, value_reg` | `lower_resume` `normalize.py:416-429` |
| `DefineExpr`（`DefeffectExpr` 值） | `DEFEFFECT name, resumable` + `LOAD_ENV dst, name` | `normalize.py:496-502` |
| `DefineExpr`（`LambdaExpr` 值） | `MAKE_FUNCTION dst, fn_idx` + `DEFINE_ONCE name, dst` | `normalize.py:504-510` |
| `DefineExpr`（一般） | lower value + `MOVE dst, value_reg` + `DEFINE_ONCE name, dst` | `normalize.py:511-516` |
| `PipelineExpr` | `lower_body`，无额外 instruction | `lower_pipeline` `normalize.py:431-433` |
| `ParallelExpr` | 每 expr 一个 thunk；`PARALLEL_GATHER dst, *thunk_indices` | `lower_parallel_all` `normalize.py:435-452` |
| `AllExpr` | 同上 + `ALL_GATHER dst, *thunk_indices`（opcode 选取行 438） | `lower_parallel_all` `normalize.py:435-452` |
| `RaceExpr` | 每 expr 一个 thunk；`RACE_FIRST dst, *thunk_indices` | `lower_race` `normalize.py:454-472` |
| `ApplyExpr` | lower fn + args + `APPLY dst, fn_reg, args_reg` | `lower_apply` `normalize.py:474-481` |
| `CacheExpr` | thunk + `CACHE_EVAL dst, cache_key, thunk_fn_idx` | `lower_cache` `normalize.py:483-491` |
| 未知节点 | 生成 diagnostic，返回 `None` register | `normalize.py:205-206` |

### 5.2 关键规则

- **`tail_position` 由 MIR lowering 推断**：HIR 阶段不设置 `tail_position`，由 `lower_call`（`normalize.py:275-282`）根据所在位置决定。
- **`MIRBlock` 划分**：`lower_perform` 显式新建 block 用于 resume；`lower_cond` 每 clause 切 block。
- **thunk 函数**：并行 / race / cache 都为每个 expr 引入独立 thunk（`lower_function` 嵌套）。
- **DEFINE_MODULE / DEFINE_ONCE**：定义发生在指令层；副作用由 VM / runtime 处理。

## §6 工作样例

### 6.1 算术

**HIR**：

```text
CallExpr {
  operator = SymbolRefExpr { symbol = +, binding = <builtin: +> }
  args = (LiteralExpr 1, LiteralExpr 2)
  tail_position = True
}
```

**MIR**（pseudo-dump 风格与 `dump_mir` 一致）：

```text
fn#0 main() entry=bb0 regs=3 [main]
  bb0:
    r0 = LOAD_CONST 1
    r1 = LOAD_CONST 2
    RETURN r2
```

具体 lowering 后：

```text
fn#0 main() entry=bb0 regs=3 [main]
  bb0:
    r0 = LOAD_CONST 1
    r1 = LOAD_CONST 2
    r2 = CALL r<+> (r0, r1)
    RETURN r2
```

要点：常数进入 `MIRConstantPool`；运算符通过 `LOAD_ENV` 加载 binding 后调用。

### 6.2 define + lambda + call

**HIR**：

```text
DefineExpr {
  name = square
  value = LambdaExpr { params = (x,) body = (CallExpr { *, x, x },) }
}
CallExpr { operator = square, args = (LiteralExpr 12,) }
```

**MIR**：

```text
constant pool:
  #0: 12

fn#0 main() entry=bb0 regs=4 [main]
  bb0:
    r0 = MAKE_FUNCTION fn#1
    DEFINE_ONCE square, r0
    r1 = LOAD_CONST 0         ; 12
    r2 = CALL r<square> (r1)
    RETURN r2

fn#1 square(x) entry=bb0 regs=4
  bb0:
    r0 = LOAD_ENV x
    r1 = LOAD_ENV x
    r2 = CALL r<*> (r0, r1)
    RETURN r2
```

要点：`defun` 在 HIR 中是 `DefineExpr(name, LambdaExpr(...))`；在 MIR 中被展为 `MAKE_FUNCTION` + `DEFINE_ONCE`；每个 lambda 独立成函数（嵌套 `lower_function`）。

### 6.3 handle + perform + resume

**HIR**：

```text
HandleExpr {
  expression = CallExpr { +, (/ 1 0), (/ 1 0) }
  handlers = (
    EffectHandler {
      effect = divide-by-zero
      arg_name = <ignored>
      continuation_name = k
      body = (ResumeExpr { k, 1 },)
    },
  )
}
```

**MIR**（伪 dump，按 `normalize.py:385-414` 描述）：

```text
constant pool:
  #0: 1
  #1: 0

fn#0 main() entry=bb0 regs=6 [main]
  bb0:
    r0 = LOAD_CONST 0   ; 1
    r1 = LOAD_CONST 1   ; 0
    r2 = CALL r</> (r0, r1)              ; 内层 / 1 0
    r3 = LOAD_CONST 0   ; 1
    r4 = LOAD_CONST 1   ; 0
    r5 = CALL r</> (r3, r4)              ; 内层 / 1 0
    r6 = CALL r<+> (r2, r5)
    EFFECT_HANDLE_BEGIN 0, fn#2, ((divide-by-zero, fn#3))
    r7 = CALL r<body-fn> ()              ; body 是包装 function
    EFFECT_HANDLE_END 0, r7
    RETURN r7

fn#2 handle-body() entry=bb0 regs=2
  bb0:
    ; 计算 + (/ 1 0) (/ 1 0) → r0
    RETURN r0

fn#3 handler-divide-by-zero(<ignored>, k) entry=bb0 regs=2
  bb0:
    r0 = LOAD_CONST 0
    EFFECT_RESUME r0, r<k>, r0
```

要点：

- 每个 `EffectHandler` 独立成 thunk 函数；
- `EFFECT_HANDLE_BEGIN/END` 包夹 handler region；body 本身是单独函数；
- `ResumeExpr` 在 handler 内产生 `EFFECT_RESUME`；
- `PerformExpr` 产生 `EFFECT_PERFORM` terminator，由 fall-through 块承载 resume 续体。

## §7 现状与偏差

### 7.1 `continuous` 标志未被 set

`MIRInstruction.continuous` 永远为 `False`：

- `normalize.py:540` 是仓库内唯一构造 `MIRInstruction` 的位置，构造时未传 `continuous=`。
- `lower_call`（`normalize.py:266-285`）读取 `tail_position` 但不读 `continuous`。
- 因此 `docs/ir-design.md §1.2` 描述的连续算子静态不变量当前**未生效**；MIR verifier 中的 `_verify_continuous_run` 永不 fire。

spec 要求 `MIRInstruction.continuous` 与 HIR `CallExpr.continuous` 一致；当前实现须补齐传播。

### 7.2 `LOAD_HOST` 直接携带 Python 对象

`LiteralExpr` 与 `QuoteExpr` 在 `normalize.py:127-134` 经 `emit_load_const` / `_quote_data` 处理后以 `LOAD_CONST` 产出，但**当前实现**实际通过后续 LIR `linearize.py:39-42` 的改写得到 `LOAD_HOST dst, value`——LIR 阶段产生直接携带 Python 对象的 `LOAD_HOST`。MIR 阶段理论上应仅承载 `LOAD_CONST` + pool index；该差距是迁移期的实现选择。

### 7.3 `LOAD_ENV` 是常见输出

HIR→MIR 阶段 `LOAD_ENV` 是绝大多数 `SymbolRefExpr` / `UnresolvedSymbolExpr` 的产物；它未被进一步 lower 成 slot 操作（应在 LIR 抽象机 lowering 中完成）。当前 LIR 阶段直接 pass-through，详见 `docs/lir-spec.md` §7。

### 7.4 无顶层独立 validator pass

`qy/passes/mir/validate.py` 调用 `verify_mir`（在 `qy/ir/mir/__init__.py`），但 MIR 阶段实际上由 `mir/normalize.py` 在 lowering 期间自检；validator 是独立 pass 调用入口。M1-M12 的检查规则在 spec 中列出，对照 `verify_mir` 实现。

### 7.5 `RUNTIME_EVAL` 与 `CACHE_EVAL` 是 compat 节点

这两个 opcode 在 MIR 中表达，但 LIR 阶段只 pass-through，未被 abstract-machine dialect 取代。MIR 这一层把它们作为一等 opcode；下游语言是否继续保留由 LIR verifier / VM 决定。