# Language-Core Audit

偏离 symbol/chain/effect 核心的实现点标记。

核心约束回顾：语法数据只有 `symbol` / `chain`；数字、字符串、Python object 不是语法类型，而是 env lookup 后得到的 runtime value；effect 是一等控制流。

---

## A1. `LiteralExpr` — HIR 引入了多 primitive type 语法节点

**位置**：`qy/ir.py:77-82`，`qy/lowering.py:162-243`

`LiteralExpr(value, type_name)` 直接把 `int`/`str`/`bool`/`None` 建模为 HIR 节点。这使得数字和字符串在语法层面成为特殊类型，而不是 env 预查找后得到的 runtime value。

**影响文件**：`ir.py`、`lowering.py`、`mir_lowering.py`、`ir_vm.py`、`evaluator.py`

**处置方向**：

- 短期：`LiteralExpr` 继续作为"host value 注入"的占位表示，但需明确语义是"宿主预注入的常量 runtime value"，不是"语言原生 primitive 语法"。
- 长期：数字、字符串字面量应通过 reader 转化为 env 中的 host value ref，或由 LIR 阶段统一处理为 `LOAD_CONST host_value`，不在 HIR/MIR 以上出现。

---

## A2. `RuntimeMetaCallExpr` — compile-time 宏语义下沉到 runtime

**位置**：`qy/ir.py:117-122`，`qy/lowering.py`，`qy/ir_vm.py`

`RuntimeMetaCallExpr` 将 macro 的 raw form 直接传递给 runtime，由 runtime 再次展开执行。这模糊了 compile-time（macroexpand 阶段）与 runtime（IR VM 阶段）的边界。

**影响文件**：`ir.py`、`lowering.py`、`ir_vm.py`

**处置方向**：

- 若所有 macro 都统一走 `macroexpand` 阶段展开，`RuntimeMetaCallExpr` 应删除（见删除候选）。
- 如果存在合法的 runtime eval-time macro case，需在 MIR 中引入显式的 `EVAL` opcode 而不是把整个 form 传递给 runtime interpreter。

---

## A3. 遗留 operator dispatch 体系 — 求值器行为 = 语言语义

**位置**：`qy/evaluator.py:83-173`

五类 operator：`PureOperator`、`ScopeOperator`、`ControlOperator`、`EffectOperator`、`MetaOperator`，均把 Python callable 包装为 Qy 语言语义。

**问题**：

- operator 的"执行方式"（纯/作用域/控制/效应/元）是求值器实现细节，不是语言核心 value 类型。
- 新代码（MIR/register VM 路径）不应再添加这些类型的 operator；所有新算子应走 bytecode + host-call 路径。

**影响文件**：`evaluator.py`、`stdlib/core.py`、`stdlib/strings.py`、`stdlib/io.py`

**处置方向**：

- 冻结：禁止继续添加新的 `PureOperator`/`ScopeOperator`/`ControlOperator`/`MetaOperator` 实例。
- 长期：MIR/LIR/bytecode/VM 接管对应语义后，降级为 compatibility shim 或删除。

---

## A4. `UserFunction` / `ComponentDefinition` — 并行的 runtime function value

**位置**：`qy/evaluator.py:217-262`

`UserFunction` 与 `ComponentDefinition` 是 legacy evaluator 的函数值类型；MIR 路径使用的是 bytecode-compiled `IRFunction`（定义在 `register_vm.py`）。

两者并存意味着：同一个 `(defun ...)` 可以在 legacy 路径产生 `UserFunction`，在 MIR 路径产生 `IRFunction`。

**处置方向**：

- 当 register VM 覆盖所有 `defun`/`lambda`/component 语义后，删除 `UserFunction` / `ComponentDefinition`，只保留 compatibility wrapper。

---

## A5. `ComponentExpr` — 半等同于 `DefunExpr`，语义未裁决

**位置**：`qy/ir.py:165-172`，`qy/mir_lowering.py`

`ComponentExpr.type_name = "function"`，MIR lowering 将其完全复用 DefunExpr 路径。这意味着 HIR 有独立节点但 MIR 以下无法区分 component 与 function。

**当前状态**："可运行，无独立表示"（见 report.md MIR-01 条目）。

**处置方向**：

- 必须裁决：component 等同 function → 删除 `ComponentExpr` 节点；component 不同 → MIR/runtime 保留 `kind=component`。
- 见 todo.md F5。

---

## A6. `list` / `tuple` 作为 core 算子 — Python 容器类型泄漏

**位置**：`qy/stdlib/core.py:112-145`

`list` 和 `tuple` 直接操作 Python 原生容器，暴露在默认 env 中。这使得调用方依赖 Python 的 `list`/`tuple` 类型而不是 Qy 的 `chain`/`cons` 模型。

**处置方向**：

- 移到 `stdlib/python.py` 或 `stdlib/host.py` 命名空间，不再进入默认 env。
- 确保 Qy 的 pair/chain 操作（`car`/`cdr`/`cons`）是主要数据接口。

---

## A7. Effect family 不在 MIR/bytecode/VM

**位置**：`qy/mir.py`（无 PERFORM/HANDLE/RESUME opcode），`qy/mir_lowering.py`，`qy/register_vm.py`

`PerformExpr`、`HandleExpr`、`ResumeExpr`、`DefeffectExpr` 仅在 HIR 中有表示；MIR lowering 遇到它们时发出 diagnostic 并拒绝执行。所有 effect 语义仍由 legacy `ir_vm.py` 承载。

这是目前最大的语言核心偏差：effect 是核心控制语义，但只在 legacy runtime 中可用。

**处置方向**：

- MIR 引入 `PERFORM`、`HANDLE_ENTER`、`HANDLE_EXIT`、`RESUME` 等 opcode（见 todo.md 任务 10）。
- LIR 阶段完成 effect frame 的 register layout。
- register VM 实现 effect continuation。

---

## A8. 其他未完整进入 MIR 的 HIR 节点

**位置**：`qy/mir_lowering.py`

以下节点在 MIR lowering 中只发出 diagnostic，无真正 MIR 表达：

- `AssertExpr`（任务 7）
- `RuntimeEvalExpr`（任务 8）
- `ModuleExpr` / `FromImportExpr`（任务 9）

---

## A9. `str-*` 暴露在全局 env

**位置**：`qy/stdlib/strings.py:27-48`

`str`、`str-len`、`str-concat` 等 14 个 operator 直接注册到默认 env。按语言核心约束，这些属于宿主 stdlib namespace，不应是默认 env 的一部分。

**处置方向**：

- 移到 `stdlib/strings` namespace，由 `(from stdlib.strings import ...)` 显式引入。
- 短期保留向后兼容，加注明文档。

---

## A10. provisional `source_modules.py` — 编译时/运行时混用模块视图

**位置**：`qy/source_modules.py`

`source_modules.py` 中的 provisional module 是语法驱动的占位对象，用于在 lowering/analyzer 时提前建立 module 可见性。真正的 runtime module 由 `ir_vm.py` 执行时注册覆盖。

**风险**：provisional module 包含 macro_exports 但缺少 complete runtime value；若调用方依赖占位 module 的值对象可执行，会静默失败。

**处置方向**：

- module system 稳定后（任务 9），合并到正式 module loader，删除 provisional 逻辑。

---

## 优先级汇总

| 编号 | 偏差                             | 优先级 | 对应任务   |
| ---- | -------------------------------- | ------ | ---------- |
| A5   | ComponentExpr 语义未裁决         | P0     | 任务 5     |
| A7   | Effect 不在 MIR/VM               | P0     | 任务 7-10  |
| A8   | HIR 节点未进 MIR                 | P0     | 任务 7-9   |
| A2   | RuntimeMetaCallExpr              | P1     | —          |
| A3   | 遗留 operator dispatch           | P1     | 任务 12/13 |
| A4   | UserFunction/ComponentDefinition | P1     | 任务 12    |
| A1   | LiteralExpr 多 primitive type    | P2     | 长期       |
| A6   | list/tuple 泄漏                  | P2     | 任务 6     |
| A9   | str-\* 全局暴露                  | P2     | 任务 6     |
| A10  | provisional source_modules       | P2     | 任务 9     |
