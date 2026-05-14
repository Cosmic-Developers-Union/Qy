# Language-Core Audit

偏离当前语言契约的实现点标记。核心约束：

- syntax datum 只有 `symbol` / `chain`。
- `chain` 是不可变对象。
- 核心语言不实现 unrestricted reader macro；默认 Qy surface dialect 是 reader 后、macroexpand 前的可静态描述规约层。
- symbol 求值沿 symbol-space-chain 查找。
- `define` 只在当前 symbol-space 一次性绑定；允许 shadow parent。
- pre-symbol-space 由 Qy 实例化决定；默认实例可以惰性预定义数字、字符串等传统符号。
- host value 是 runtime value，可以通过实例 pre-symbol-space、显式注入或显式 import 进入 symbol-space-chain。
- register VM 是唯一执行器；不保留可选 runtime backend。

---

## B1. 多 backend 残留

**位置**：`qy/runtime.py`、`qy/ir_vm/`、`qy/evaluator.py`、`qy/__init__.py`、`tests/test_ir_vm.py`

当前仍有 `EvaluationBackend = "ir" | "bytecode"`、`Qy(backend=...)`、`evaluate_ir_*` 与 IR VM public API。  
这与“只保留 register VM”的裁决冲突。

**处置方向**：

- 删除 backend 参数与 backend 类型。
- 公共执行入口固定走 register VM。
- IR VM / legacy evaluator 从 public API 中移除，进入删除队列。
- tests/examples/benchmark 不再比较或依赖 IR backend。

---

## B2. `define` 查重边界过宽

**位置**：`qy/lowering.py`、`qy/analyzer.py`、`qy/register_vm.py`

`define_once` 已存在，但 lowering 里的 top-level define 检查会查 parent scope，导致 `define` 不能 shadow 外层符号。  
最新语言契约要求：`define` 只检查当前 symbol-space，允许 shadow parent 中的核心、stdlib、pre-symbol-space、host 注入名。

**处置方向**：

- lowering/analyzer/runtime 全部改为 current-space-only define。
- 默认数字/字符串 pre-symbol-space 需要显式建模或惰性建模；同一空间不能 redefine，子空间可以 shadow。
- `defun`、`defeffect`、module import/export 同步使用 current-space-only define-once。
- register VM 的 `STORE_LOCAL`、`DEFEFFECT`、module/import 写入也要按 define-once 语义收口。

---

## B3. pre-symbol-space 与 host interop 边界未清

**位置**：`qy/stdlib/__init__.py`、`qy/stdlib/core.py`、`qy/stdlib/python.py`

当前默认 prelude 仍包含 `qy.py`，`qy.core` 也合入 `python_operators()`，因此 `py`、`list`、`tuple`、`dict`、`set` 仍会进入默认 symbol-space。

**偏差**：默认数字/字符串 pre-symbol-space 是合理实现策略；但 Python host interop prelude 不应与它混在一起。analyzer/LSP 也需要能读取当前 Qy 实例的 pre-symbol-space 配置。

**处置方向**：

- 明确 default resolver / pre-symbol-space API：数字、字符串等传统符号可惰性预定义。
- 默认 prelude 只加载最小语言 core，不自动加载 Python host interop。
- `qy.py`、Python container helper、string helper、legacy async helper 全部改为显式 import 或显式 host injection。
- 示例和测试中需要 host interop 时显式构造 env 或 import module。

---

## B4. 新 HIR 节点尚未接入 register VM 主路径

**位置**：`qy/mir_lowering.py`

`DefineExpr` 已部分 lower；但 `PipelineExpr`、`ParallelExpr`、`AllExpr`、`RaceExpr`、`ApplyExpr` 仍在 MIR lowering 中产生 unsupported diagnostic。  
这些节点在 IR VM 中可运行不算验收，因为 IR VM 不再是 backend。

**处置方向**：

- 为这些 HIR 节点补 MIR/LIR/bytecode/register VM 语义。
- examples validation 不能依赖 IR backend 验收这些核心语义。

---

## B5. `component` / legacy API 残留

**位置**：`qy/lowering.py`、`qy/analyzer.py`、`qy/lsp.py`、`qy/operator_signature.py`、`docs/op.md`、`tests/*`

`component` 已从默认环境移到 legacy module，但 HIR/lowering/analyzer/LSP/docs/tests 中仍有核心级路径或说明。

**处置方向**：

- `component` 从核心语义、签名、LSP snippet、文档中删除。
- legacy module 可保留兼容测试，但不得作为语言核心验收。

---

## B6. `RuntimeMetaCallExpr`

**位置**：`qy/ir.py`、`qy/lowering.py`、`qy/ir_vm/`

`RuntimeMetaCallExpr` 把 macro raw form 传给 runtime 再展开，模糊 compile-time 与 runtime 边界。

**处置方向**：

- macro 统一在 expand 阶段完成。
- runtime eval 只能走显式 `eval` / `RuntimeEvalExpr` / VM opcode，不得复用 meta call。

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

| 编号 | 偏差                                 | 优先级 |
| ---- | ------------------------------------ | ------ |
| B1   | 多 backend 残留                      | P0     |
| B2   | `define` 查 parent，不能 shadow 外层 | P0     |
| B3   | 默认环境加载 host interop            | P0     |
| B4   | 新 HIR 节点未进入 register VM        | P0     |
| B5   | `component` / legacy API 残留        | P1     |
| B6   | `RuntimeMetaCallExpr`                | P1     |
| B7   | 遗留 operator dispatch               | P1     |
| B8   | Python codegen 绕过 MIR/LIR          | P2     |
