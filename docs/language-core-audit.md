# Language-Core Audit

偏离 symbol/chain/effect 核心的**当前真实**实现点标记。已修复或与语言契约一致的历史问题不在此列。

核心约束回顾：语法数据只有 `symbol` / `chain`；binding 一次性，不可在同一 symbol-space 内重绑定；effect 是一等控制流；pipeline 固定为 `source -> ast -> expand -> HIR -> MIR -> LIR -> bytecode -> register VM`。

---

## B1. `define` 语义未落地

**位置**：`qy/environment.py`、`qy/stdlib/core.py`

`define` 当前是可重绑定的 `set`，没有一次性约束。`Environment` 缺少 `define_once` API；同一 symbol-space 内重复 `define` 不报错。host 注入的 symbol 也可被 `define` 覆盖。

**偏差**：违反语言契约"同一 symbol-space 内不可重绑定"。

**处置方向**（P0-2）：
- `Environment` 增加 `define_once`；重复绑定时报错。
- host 注入路径标记 symbol 已绑定。
- analyzer 诊断重复 `define`。

---

## B2. 旧 core 暴露：`spawn`、`await`、`component`

**位置**：`qy/stdlib/core.py`、`qy/ir.py`（`ComponentExpr`）

语言契约明确不含 `spawn` / `await` / `component`，但三者仍注册在默认 core 环境中，可直接使用。

**偏差**：默认 core 与 `LANGUAGE.md` / `todo.md` 核心算子表不一致。

**处置方向**（P0-3）：
- 从默认 core 移除 `spawn`、`await`、`component`。
- 删除 `ComponentExpr` HIR 节点。
- 相关 operator signature / LSP / test 残留一并清理。

---

## B3. 旧 core 暴露：`list`、`tuple`、`dict`、`set`、`str-*`

**位置**：`qy/stdlib/core.py:112-145`、`qy/stdlib/strings.py:27-48`

Python 容器 helper 与字符串 helper 直接注册到默认 env，使调用方依赖 Python 原生类型而不是 Qy chain/cons 模型。

**偏差**：默认 core 超出语言核心算子集合。

**处置方向**（P0-3 / P2-1）：
- 容器 helper 移到 `py::list`、`py::tuple` 等显式 namespace。
- string helper 移到 `str` namespace，由显式 import 引入。

---

## B4. `RuntimeMetaCallExpr`

**位置**：`qy/ir.py`、`qy/lowering.py`、`qy/ir_vm/`

`RuntimeMetaCallExpr` 把 macro 的 raw form 传递给 runtime 再次展开，模糊了 compile-time（macroexpand 阶段）与 runtime 的边界。

**偏差**：编译与执行边界不清晰。

**处置方向**（P0-4）：
- 若所有 macro 统一走 macroexpand 阶段，删除 `RuntimeMetaCallExpr`。
- 若存在合法 runtime eval 场景，在 MIR 引入显式 `EVAL` opcode 而非传递整个 form。

---

## B5. 遗留 operator dispatch 体系

**位置**：`qy/evaluator.py:83-173`、`qy/stdlib/`

`PureOperator`、`ScopeOperator`、`ControlOperator`、`EffectOperator`、`MetaOperator` 把 Python callable 包装为 Qy 语义，仍是大量 stdlib 的实现方式。

**偏差**：新算子应走 bytecode + host-call ABI，不得继续使用 legacy dispatch 类型。

**处置方向**（P1-3）：
- 冻结：禁止继续新增这些类型的 operator 实例。
- MIR/LIR/bytecode/VM 接管对应语义后，降级为 compatibility shim 或删除。

---

## B6. Python codegen 绕过 MIR/LIR

**位置**：`qy/python_codegen.py`

`codegen_python` 直接从 HIR（`ProgramIR`）生成 Python 代码，跳过了 MIR/LIR 阶段。这是 prototype 实现，但不是主 pipeline。

**偏差**：bytecode compiler 禁止重新理解 HIR 语义，HIR -> Python codegen 同样违反此约束。

**处置方向**（P2-2）：
- CLI 与文档标注为 experimental。
- 中期决定是否改为从 MIR/LIR 输入。
- 不允许 Python codegen 重新定义 effect / let / quote 语义。

---

## B7. Effect continuation 未在 MIR/register VM 落地

**位置**：`qy/mir_lowering.py`、`qy/register_vm.py`

`PerformExpr`、`HandleExpr`、`ResumeExpr`、`DefeffectExpr` 在 MIR lowering 中只发出 diagnostic，无真正 MIR 表达。Effect 语义仍由 legacy `ir_vm/` 承载。

**偏差**：effect 是核心控制语义，但 register VM 无法执行任何 effect 代码。

**处置方向**（P0-6 / P1-1）：
- MIR 引入 `PERFORM`、`HANDLE_ENTER`、`HANDLE_EXIT`、`RESUME` opcode。
- LIR 完成 effect frame register layout。
- register VM 实现 effect continuation。

---

## 优先级汇总

| 编号 | 偏差                                      | 优先级 | 对应任务 |
| ---- | ----------------------------------------- | ------ | -------- |
| B1   | `define` 未落地（可重绑定）               | P0     | P0-2     |
| B2   | `spawn`/`await`/`component` 在默认 core   | P0     | P0-3     |
| B3   | `list`/`tuple`/`str-*` 在默认 core        | P0     | P0-3     |
| B4   | `RuntimeMetaCallExpr`                     | P0     | P0-4     |
| B5   | 遗留 operator dispatch 体系               | P1     | P1-3     |
| B6   | Python codegen 绕过 MIR/LIR               | P2     | P2-2     |
| B7   | Effect continuation 未在 MIR/register VM  | P0     | P0-6     |
