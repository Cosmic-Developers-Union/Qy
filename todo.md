# Qy TODO

基线：`05aac18 feat: 推进 MIR`。验证：`pytest -q` 278 passed；`make lint` passed。

## 语言核心

Qy 的核心不是“Python 宿主上的 Lisp”，而是一个极小语法数据模型 + 一等 runtime value 模型：

- Everything is symbol。
- 语法数据核心只有 `symbol` 与 `chain`。
- 符号在同一空间内不可重绑定；`define` 是常量绑定，不是 `set`。
- Runtime value 存在于 env 预空间，由 `number`、`string`、`object` 构成；`number` 与 `string` 是特殊 object。
- Host value 是一等 runtime value，Qy 可以直接操作。
- 代数效应是核心控制语义，不是 stdlib exception 包装。
- Qy 由 Python 实现，但目标语言是 like-Lisp + algebraic effects，不是 Python DSL。
- 目标执行器是 register VM；IR VM 是过渡期 reference runtime，不是最终主执行器。

核心算子集合：

| 类别          | 算子                                                  |
| ------------- | ----------------------------------------------------- |
| syntax datum  | `quote`                                               |
| pair/chain    | `atom`、`eq`、`car`、`cdr`、`cons`                    |
| binding/scope | `define`、`let`                                       |
| control       | `cond`                                                |
| ordering/join | `pipeline`、`parallel`、`race`、`all`                 |
| function      | `defun`、`lambda`、`apply`                            |
| macro         | `macro`、`quasiquote`、`unquote`、`gensym`、`capture` |
| effect        | `defeffect`、`perform`、`handle`、`resume`            |
| module        | `module`、`from`、`import`、`exports`                 |

核心算子语义约束：

- `define` 构建一次性绑定；只能绑定当前 symbol-space 中不存在的 symbol，并保护当前 symbol-space 内已绑定的 symbol。
- `let` 构建局部 symbol-space，可以绑定任意 symbol，包括外层已有 symbol、核心算子名、宿主注入名。
- 外部宿主可以通过注入 symbol-space 来注入 object(host value) 与 operator。
- `pipeline` 是 begin/end 风格的串行求值 form，返回最后一个表达式。
- `parallel` 是 parallel-map 风格的 order-insensitive 求值组；允许 VM 并行求值，但不要求并行；支持 effect。
- `all` 是 barrier continuation；全部分支完成后恢复 parent continuation。
- `race` 是 first-resume wins；最先恢复 parent continuation 的分支决定结果。
- `+`、`-` 等纯算术算子暂不进入核心算子集合；它们应来自宿主预空间或 stdlib/operator namespace。

目标管线：

```text
source
  -> ast
  -> expand
  -> HIR
  -> MIR
  -> LIR
  -> bytecode
  -> register VM
```

层次职责：

- AST：reader 输出的 syntax datum。
- Expand：macro 展开，输入/输出仍是 syntax datum。
- HIR：高层语义 IR，完成 binding、operator signature、effect signature、module/macro 语义承接。
- MIR：CFG / virtual register IR，表达控制流、tail call、effect control flow。
- LIR：低层 register VM IR，完成 register layout、opcode lowering、host-call lowering、effect frame lowering。
- bytecode：register VM 的最终指令序列，不重新理解 HIR/MIR 语义。

架构约束：

- reader / AST 可以保留表面语法信息，但 syntax datum 只能落到 `symbol` / `chain`。
- 数字、字符串、Python object 不是额外语法数据类型；它们是 env lookup 后得到的 runtime value，或 host interop 引入的一等 object。
- analyzer 的类型信息是对 symbol/chain、binding、runtime value、operator signature、effect 的静态推断。
- 因为符号不可重绑定，HIR 阶段允许对可确定 binding 做预查找，把 symbol ref 解析为稳定 binding/value，这是后续优化基础。
- macro 是 compile-time 的 symbol/chain -> symbol/chain 改写，必须有 hygiene、definition-site binding、module compile-time scope。
- MIR / LIR / bytecode / VM 不能重新引入“literal-first”的语言模型；它们必须显式区分 syntax datum、env lookup、runtime value 与 effect 控制流。
- stdlib 可以扩展 runtime 预空间、命名空间与 host interop，但不能反向定义语法核心。

当前偏差风险：

- `LiteralExpr`、`int`、`str-*`、list/tuple 风格 operator 容易把语言带回多 primitive type 模型。
- 但 runtime `number` / `string` / `object` 是合法的一等值；风险在于把它们建模成语法核心类型，而不是 lookup 后的 runtime value。
- `RuntimeMetaCallExpr` 会把 compile-time macro 语义拖回 runtime。
- `UserFunction` / legacy operator class 会继续把“求值器行为”当作语言语义。
- effect family 还没有在 MIR/bytecode/register VM 中成为一等控制流。

## 状态判断

代码推进很快，但复杂度收敛不足。问题不是提交方式，提交由维护者处理；后续只按“任务批次”约束：每个批次只解决一个架构问题，并在 `report.md` 说明范围、风险、验证。

当前高风险文件：

| 文件                   | 风险                                   |
| ---------------------- | -------------------------------------- |
| `stdlib/core.py` ~9.6k | stdlib 大杂烩，必须拆模块              |
| `evaluator.py` ~7.8k   | legacy runtime/value/operator 混在一起 |
| `macroexpand.py` ~7.2k | 正在变成新的中心化 evaluator           |
| `ir_vm.py` ~6.7k       | 调用、模块、effect、eval 混杂          |
| `lowering.py` ~6.6k    | HIR lowering 与环境/module 逻辑耦合    |
| `analyzer.py` ~6.0k    | 与 lowering 语义重复，容易漂移         |

复杂度规则：

- 超过 6k tokens 的文件进入“冻结增长”状态：只允许修 bug 或拆分，不继续塞新语义。
- 超过 8k tokens 的文件必须优先拆分。
- 新功能必须落到明确阶段：macroexpand / HIR / MIR / LIR / bytecode / VM，不能跨层补丁式扩散。

## 当前阻塞

### F1. Module Macro Definition-Site Binding 不完整

复现：

```lisp
(module review.localmacro
  (defun helper (x) (+ x 1))
  (macro call-helper (value)
    (cons 'helper (cons value '())))
  (exports call-helper))
(from review.localmacro import call-helper)
(call-helper 41)
```

当前：`unresolved symbol 'helper'`。

原因：

- `source_modules.py` provisional macro closure 是外层 env。
- module body macro 在 `macroexpand.py` 中也捕获外层 `context.env`。
- hygiene 的 definition-site lookup 只查 macro closure，找不到 module-local helper。

验收：

- 导出 macro 可引用定义模块内未导出的 helper。
- 或者明确禁止，并给 compile-time diagnostic。
- 先补失败测试，再修实现。

### F2. Hygiene Alias 泄漏到 Runtime Namespace

当前 `_definition_site_alias` 通过 `context.env.define(alias, value)` 落地。

风险：

- REPL completion / debug dump / reflection 会看见 `__qy_hygiene_def_*`。
- compile-time binding 泄漏到 runtime value namespace。

验收：

- hidden alias 不进入普通 `Environment.bindings()`。
- alias 由 compile-time namespace 或 compiler alias table 管理。
- source map 仍能显示 original -> rewritten。

### F3. `macroexpand.py` 必须拆分

拆分目标：

- `macro_scope.py`：macro namespace、module macro import/export。
- `macro_hygiene.py`：rename/capture/definition-site alias。
- `macro_trace.py`：trace/source map/diagnostics chain。
- `macroexpand.py`：只做 orchestration。

验收：

- `macroexpand.py` 降到编排层。
- hygiene 有独立单元测试。
- module scope 与 hygiene rewrite 不互相嵌套。

### F4. MIR/LIR 仍未接管核心语言

已支持：

- literal / quote / symbol
- call / tail call
- let / cond
- defun / lambda
- macro no-op
- component as function

缺口：

- `AssertExpr`
- `RuntimeEvalExpr`
- `ModuleExpr`
- `FromImportExpr`
- `DefeffectExpr`
- `PerformExpr`
- `HandleExpr`
- `ResumeExpr`

顺序：

1. `AssertExpr`
2. `RuntimeEvalExpr`
3. `ModuleExpr` / `FromImportExpr`
4. effect family

每补一个节点必须覆盖 MIR dump、verifier、LIR dump、bytecode、VM、CLI debug 输出。

### F5. Component 语义必须裁决

当前 `ComponentExpr` 复用 function lowering。

裁决：

- 如果 component 等同 function：删除独立 runtime value / IR 节点。
- 如果 component 不同：MIR/bytecode/runtime value 必须保留 `kind=component`。

不能继续“半等同”。

## 删除候选

这些不是马上删，而是必须进入清理评审。

| 候选 | 删除/保留条件 |
| --- | --- |
| legacy AST evaluator helpers | register VM 覆盖对应语义后删除，只保留 compatibility wrapper |
| `evaluate_body_async` | stdlib/core 不再依赖后删除 |
| `UserFunction` / `ComponentDefinition` | IRFunction/bytecode value 接管后删除或迁移 |
| `ScopeOperator` / `ControlOperator` / `MetaOperator` | operator metadata 接管 dispatch 后删除或降级 shim |
| `RuntimeMetaCallExpr` | 若语法扩展统一走 macroexpand，应删除 |
| `ComponentExpr` | 若 component 无独立语义，应删除 |
| `str-*` core exposure | 移到 stdlib namespace，不属于 core |
| provisional `source_modules.py` 逻辑 | module system 稳定后合并到正式 module loader 或删除 |

## 拆分计划

### S1. `stdlib/core.py`

拆成：

- `stdlib/arithmetic.py`
- `stdlib/data.py`
- `stdlib/control.py`
- `stdlib/effects.py`
- `stdlib/python.py`
- `stdlib/modules.py`

目标：`core.py` 只聚合注册，不承载实现。

### S2. `evaluator.py`

拆成：

- `environment.py`
- `operators.py`
- `runtime_values.py`
- `continuation.py`
- `legacy_evaluator.py`

目标：新代码不再 import runtime 类型自 `evaluator.py`。

### S3. `ir_vm.py`

拆成：

- `ir_vm/core.py`
- `ir_vm/calls.py`
- `ir_vm/effects.py`
- `ir_vm/modules.py`
- `ir_vm/runtime_eval.py`

目标：主 VM 文件只保留 frame loop / dispatch。

### S4. `lowering.py` 与 `analyzer.py`

短期不大拆，先抽共享语义：

- module import/export resolution
- operator metadata lookup
- binding/scope model

目标：analyzer 与 lowering 不再各写一套 `from/module` 规则。

## 下一步顺序

1. 建立 language-core audit：标记所有偏离 symbol/chain/effect 核心的实现点。
2. 修 `F1`。
3. 修 `F2`。
4. 拆 `macroexpand.py`，先抽 `macro_hygiene.py`。
5. 裁决 `F5` component。
6. 拆 `stdlib/core.py`。
7. 补 `AssertExpr` MIR/LIR/bytecode/VM。
8. 补 `RuntimeEvalExpr`。
9. 补 `ModuleExpr` / `FromImportExpr`。
10. 设计 effect MIR。
11. 设计并落地 LIR 层，禁止 bytecode compiler 直接重新理解 MIR 以上语义。
12. 拆 `evaluator.py`。
13. 拆 `ir_vm.py`，并把它降级为 reference runtime / compatibility layer。
14. primitive opcode 必须重新命名/定义为 host opcode，不得暗示核心 primitive type。
15. benchmark gate。
16. Python codegen。

## 工作约束

- 一个任务批次只处理一个编号。
- 每个任务批次更新 `report.md`。
- `report.md` 必须写：范围、完成、未完成、风险、验证。
- 禁止在同一任务批次混改 macro hygiene、MIR lowering、VM runtime。
- 禁止新增绕过 pipeline 的执行路径。
- 禁止让 bytecode compiler 重新理解 HIR/MIR；语义 lowering 必须经由 LIR。

## 验证

普通：

```shell
uv run python -m pytest -q
make lint
```

macro：

```shell
uv run python -m pytest tests/test_eval_macro.py tests/test_macroexpand.py tests/test_module_import.py tests/test_analyzer_scope.py -q
```

MIR / LIR / bytecode / VM：

```shell
uv run python -m pytest tests/test_mir.py tests/test_register_vm.py tests/test_runtime.py -q
```

性能：

```shell
make bench
```
