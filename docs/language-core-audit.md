# Language-Core Audit

偏离当前语言契约的实现点标记。核心约束：

- syntax datum 只有 `symbol` / `chain`。
- `chain` 是不可变对象。
- 核心语言不实现 unrestricted reader macro；默认 Qy surface dialect 是 reader 后、macroexpand 前的可静态描述规约层。
- symbol 求值沿 symbol-space-chain 查找。
- `define` 只在当前 symbol-space 一次性绑定；允许 shadow parent。
- pre-symbol-space 不是语言设计目标本身，但它是标准实现的实例起点；reader、analyzer、LSP、lowering、runtime 都必须围绕同一个 `Qy` 实例工作。默认实例可以惰性预定义数字、字符串等传统符号。
- host value 是 runtime value，可以通过实例 pre-symbol-space、显式注入或显式 import 进入 symbol-space-chain。
- register VM 是唯一执行器；不保留可选 runtime backend。

---

## B1. 多 backend 残留（已完成）

**位置**：`qy/runtime.py`、`qy/evaluator.py`、`qy/__init__.py`、`tests/test_register_vm_semantics.py`、`README.md`

`qy.ir_vm/` 已物理删除，`Qy(backend=...)` / `EvaluationBackend` 已删除，`Qy.evaluate_*`、macro compile-time 和 benchmark 主路径统一走 register VM。当前没有可选 backend。

**处置方向**：

- 保持 register VM 唯一执行器约束，禁止新增 backend 回归。

---

## B2. `define` 查重边界过宽

**位置**：`qy/lowering.py`、`qy/analyzer.py`、`qy/register_vm.py`

`define_once` 已存在，且 lowering / analyzer 已改成 current-scope-only 诊断；`(define + 99)` 这类 parent shadow 现在允许。剩余问题主要在 module/import 的 define-once 规则还没有完全统一到 current-space-only 语义。

**处置方向**：

- 继续把 module/import/export 写入语义统一到 current-space-only define。
- 默认数字/字符串 pre-symbol-space 需要显式建模或惰性建模；同一空间不能 redefine，子空间可以 shadow。
- `defun`、`defeffect`、module import/export 同步使用 current-space-only define-once。
- register VM 的 `STORE_LOCAL`、`DEFEFFECT`、module/import 写入也要按 define-once 语义收口。

---

## B3. pre-symbol-space 与 host interop 边界未清

**位置**：`qy/stdlib/__init__.py`、`qy/stdlib/core.py`、`qy/stdlib/python.py`

默认 prelude 已经不再自动加载 `qy.py`，且 `qy.core` 也不再暴露 `list`、`tuple`、`dict`、`set`。剩余问题是 pre-symbol-space 仍未形成显式可读模型，analyzer/LSP 也还不能消费实例化配置。

**偏差**：默认数字/字符串 pre-symbol-space 是合理实现策略；但 Python host interop prelude 不应与它混在一起。analyzer/LSP 也需要能读取当前 Qy 实例的 pre-symbol-space 配置。

**处置方向**：

- 明确 pre-symbol-space API：数字、字符串等传统符号可惰性预定义；reader、analyzer、LSP、lowering、runtime 都从实例读取同一份起点事实。
- 默认 prelude 只加载最小语言 core，不自动加载 Python host interop。
- `qy.py`、Python container helper、string helper、legacy async helper 全部改为显式 import 或显式 host injection。
- 示例和测试中需要 host interop 时显式构造 env 或 import module。

---

## B4. 新 HIR 节点接入 register VM 主路径

**位置**：`qy/mir_lowering.py`、`qy/register_vm.py`

`PipelineExpr`、`ParallelExpr`、`AllExpr`、`RaceExpr`、`ApplyExpr`、`CacheExpr` 已有 lowering 和 VM 路径。当前残留点主要是 legacy operator dispatch 与少量 runtime helper 的共存，而非 backend 分叉。

**处置方向**：

- 保持这些节点的 MIR/LIR/bytecode 路径稳定。
- 逐步移除 legacy evaluator / IR VM 对同类语义的重复实现。

---

## B5. `component` / legacy API 残留

**位置**：`qy/lowering.py`、`qy/analyzer.py`、`qy/lsp.py`、`qy/operator_signature.py`、`docs/op.md`、`tests/*`

`component` 已从默认环境移到 legacy module，且已从 lowering、analyzer、macro hygiene、source module 建模、LSP snippet 与核心测试路径中移除专门分支。当前只保留 legacy module 显式引入兼容语义。

**处置方向**：

- `component` 从核心语义、签名、LSP snippet、文档中删除。
- legacy module 可保留兼容测试，但不得作为语言核心验收。

---

## B6. `RuntimeMetaCallExpr`（已完成）

**位置**：`qy/ir.py`、`qy/lowering.py`、`qy/mir.py`、`qy/register_vm.py`

`RuntimeMetaCallExpr` 与 `RUNTIME_META_CALL` opcode 已删除。meta operator 仅允许在 macro expand 阶段执行，运行期调用会产出诊断并失败。

**处置方向**：

- 继续保持 compile-time / runtime 边界，不回引 runtime meta call。

---

## B7. 遗留 operator dispatch 体系

**位置**：`qy/operators.py`、`qy/evaluator.py`、`qy/stdlib/`

`PureOperator`、`ScopeOperator`、`ControlOperator`、`EffectOperator`、`MetaOperator` 仍承载大量 stdlib 和核心行为。

**处置方向**：

- 新核心语义不得继续通过 legacy operator dispatch 实现。
- operator metadata + MIR/LIR/register VM host-call ABI 接管后，legacy dispatch 删除或降级为外部 host adapter。

---

## B8. Python codegen 绕过 MIR/LIR

**位置**：`qy/python_codegen.py`

`codegen_python` 直接从 HIR 生成 Python。它可以暂时作为 prototype，但不是主 pipeline。

**处置方向**：

- 标注 experimental。
- 后续若保留 AOT backend，必须明确输入层级，避免重新解释 HIR 语义。

---

## 优先级汇总

| 编号 | 偏差 | 优先级 | 状态 |
| --- | --- | --- | --- |
| B1 | 多 backend / 兼容 API 残留 | P0 | 已完成 |
| B2 | `define` 查 parent，不能 shadow 外层 | P0 | 部分完成 |
| B3 | 默认环境加载 host interop | P0 | 部分完成 |
| B4 | 新 HIR 节点未完全收口到唯一执行链 | P0 | 部分完成 |
| B5 | `component` / legacy API 残留 | P1 | 已缓解（仅 legacy 显式引入） |
| B6 | `RuntimeMetaCallExpr` | P1 | 已完成（节点与 opcode 已删除） |
| B7 | 遗留 operator dispatch | P1 | 待处理 |
| B8 | Python codegen 绕过 MIR/LIR | P2 | 待处理 |
