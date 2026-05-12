# Qy TODO

本文档记录 Qy 接下来一段时间的架构收敛和协作计划。

最近 review 基于当前 HEAD：

- `8a613ed feat: 优化宏和MIR`
- 开始 review 时工作区干净；本次只更新本文档。

## 协作规则

### R1. 每次修改后必须更新 `report.md`

后续每个实现者完成一次修改后，必须更新仓库根目录的 `report.md`。这不是可选项。

建议格式为倒序追加，每条记录包含：

- 时间、作者、分支或 commit。
- 对应的 TODO 编号，例如 `MIR-02`、`MACRO-03`。
- 修改文件列表。
- 主要设计决策。
- 已完成内容。
- 未完成内容。
- 风险和兼容性影响。
- 验证命令与结果，例如 `make lint`、`uv run python -m pytest`、`make bench`。

如果只改文档，也要写明“未运行测试，原因：文档修改”。

review 时我会优先读 `report.md`，然后再用 git diff/log 校验实际变更。

### R2. 不要让架构重新发散

- 不要绕过 `HIR -> MIR -> Bytecode -> Register VM` 这条线新增执行路径。
- 不要让 bytecode compiler 重新理解 HIR。
- 不要让 macro 系统进一步依赖旧 evaluator。
- 不要在 MIR 稳定前推进 Python codegen、AOT 或 JIT。
- 不要急着删除 IR VM。IR VM 仍是当前语义最完整的参考实现。
- 不要先做 SSA。当前 virtual register MIR 足够支撑 register VM 和 codegen 原型。

## 当前架构状态

当前公开管线已经形成：

```text
read
  -> macroexpand
  -> lower (HIR / ProgramIR)
  -> lower_mir (MIR / CFG)
  -> compile_bytecode
  -> RegisterVirtualMachine
```

当前判断：

- 方向正确。MIR 作为 HIR 和 bytecode 之间的 CFG 层已经出现，后续 JIT/AOT/codegen 可以稳定消费 MIR。
- `dump_mir` 已经实现，MIR 可读性比之前好很多。
- benchmark 已经拆出 `macroexpand`、`hir_lower`、`mir_lower`、`bytecode_compile`、`bytecode_vm` 阶段。
- `MacroDefinition.expand` 已经不再直接调用旧 `evaluate_body_async`，改为 `lower + IR VM` 执行 macro body。
- 主要技术债仍是 `evaluator.py`：它还承载 runtime value、operator class、Environment、legacy API、部分 stdlib helper。
- macro 系统仍处于过渡期：已有局部 macro scope、trace、source_map 雏形，但模块级 macro、hygiene、compile-time runtime 还没闭合。
- Register VM 是实验后端：可以跑核心 eager 子集和自尾递归，但 module/effect/component/eval/assert 等语义还未覆盖。

## 已完成或基本完成

### DONE-01. Pipeline API 初步公开

已具备：

- `Qy.read`
- `Qy.macroexpand_source`
- `Qy.lower`
- `Qy.lower_mir`
- `Qy.compile_bytecode`
- `Qy.evaluate_bytecode`
- `Qy(backend="bytecode")`

剩余意见：

- `compile_bytecode(program: ProgramIR)` 当前内部会再次 `lower_mir`。
- 如果调用方已经拿到 MIR，应该有公开入口复用 MIR，例如 `compile_mir_bytecode` 或 `Qy.compile_mir_bytecode`。

### DONE-02. MIR CFG 骨架

已具备：

- `MIRProgram`
- `MIRFunction`
- `MIRBlock`
- `MIRInstruction`
- `MIRTerminator`
- `TAIL_CALL` 作为 terminator。
- `dump_mir(program)`。

剩余意见：

- MIR 还不是完整语言 MIR，只覆盖当前 bytecode 子集。
- effect/module/component/assert/eval 等 HIR 节点还没有 MIR 表达。

### DONE-03. Benchmark 阶段拆分

已具备：

- `source`
- `macroexpand`
- `hir_lower`
- `mir_lower`
- `ir`
- `bytecode_compile`
- `bytecode_vm`

剩余意见：

- baseline 已存在，但还需要 CI gate 策略。
- bytecode 不支持的 case 当前会跳过，这对早期合理，但长期需要明确报告跳过原因。

### DONE-04. Macro trace/source map 雏形

已具备：

- macro expansion trace。
- nested macro trace。
- `generated_symbols`。
- `source_map` 基本入口。
- 默认 `effect_policy="deny"`。

剩余意见：

- 这还不是完整 source map，只是 expansion 事件表。
- diagnostics 还需要同时指向 call site 和 macro definition site。

## P0：协作与结构稳定

### P0-01. 建立 `report.md`

要求：

- 在仓库根目录新增并维护 `report.md`。
- 每次实现变更后更新。
- 每条记录必须引用本文档中的任务编号。

完成标准：

- `report.md` 存在。
- 最近一次实现变更有对应记录。
- 记录中包含验证命令和结果。

### P0-02. API 边界文档

要求：

- README 里已有 pipeline 图，但需要再补一份更稳定的架构文档。
- 建议新增 `docs/pipeline.md`，明确每层输入输出：
  - reader form
  - macroexpanded form
  - HIR / `ProgramIR`
  - MIR / CFG
  - bytecode
  - VM result

完成标准：

- 文档说明每层是否允许 diagnostics。
- 文档说明每层是否依赖 `Environment`。
- 文档明确 bytecode backend 的实验状态。

### P0-03. Public API 收敛

要求：

- 明确哪些 API 是稳定 API，哪些是兼容 API。
- 当前 `qy/__init__.py` 仍大量 re-export `evaluator.py` 中的旧符号，需要标记迁移路线。
- 考虑公开 `compile_mir_bytecode`，避免已经有 MIR 的调用方重复 lower。

完成标准：

- `__all__` 中稳定 API 与 legacy API 有清晰分组或文档。
- 新 API 不再鼓励直接使用旧 evaluator。

### P0-04. CLI 调试管线命令

要求：

- 给 CLI 增加调试用子命令，方便直接观察各阶段产物。
- 建议命令：
  - `qy expand <file>`：读取源码并输出 macroexpand 后的 form/AST。
  - `qy hir <file>`：输出 HIR / `ProgramIR`。
  - `qy mir <file>`：输出 MIR CFG，复用 `dump_mir`。
  - `qy bytecode <file>`：输出 bytecode function、register count、instruction list。
- 每个命令都应支持 stdin，例如 `qy mir -`。
- 每个命令都应保留 source span / diagnostics 信息，方便定位问题。
- 输出格式先用人类可读文本；后续可以增加 `--json` 供 LSP、CI 或工具消费。

完成标准：

- 四个命令都有 smoke test。
- diagnostics 不会被吞掉，错误时有清晰退出码。
- README 或 `docs/pipeline.md` 有示例。
- 输出格式稳定到足够支持 review，不要求一开始就是最终序列化格式。

## P1：MIR 完整化

### MIR-01. MIR 覆盖所有 HIR 节点

当前 `lower_mir` 只覆盖：

- literal
- quote
- symbol ref
- defun
- lambda
- macro
- let
- cond
- call / tail call

缺口：

- `AssertExpr`
- `RuntimeEvalExpr`
- `RuntimeMetaCallExpr`
- `ComponentExpr`
- `DefeffectExpr`
- `ModuleExpr`
- `FromImportExpr`
- `PerformExpr`
- `HandleExpr`
- `ResumeExpr`

完成标准：

- 每个 HIR 节点要么有 MIR 表达，要么产生明确 diagnostic。
- 不支持的节点不能静默降级为 `LOAD_CONST None`。
- `tests/test_mir.py` 覆盖上述节点的 lowering 行为。

### MIR-02. MIR verifier

要求：

- 增加 MIR verifier，检查 CFG 合法性。
- 检查每个 block 必须有 terminator。
- 检查 jump target 存在。
- 检查 `TAIL_CALL` 只出现在 terminator。
- 检查 register 使用不超过 `register_count`。

完成标准：

- 有 `verify_mir(program)` 或等价 API。
- bytecode compile 前可运行 verifier。
- verifier diagnostics 可进入 `MIRProgram.diagnostics` 或独立结果。

### MIR-03. MIR effect model

要求：

- 设计 `perform/handle/resume` 在 MIR 中的表达。
- 明确 handler stack 是 VM frame 状态，还是 MIR 显式控制流。
- 明确 continuation 是 runtime value、bytecode label，还是 VM continuation frame。

完成标准：

- MIR 中能表达 effect 操作。
- Register VM 能跑现有 effect 测试子集。
- IR VM 与 Register VM 的 effect 行为一致。

## P2：Macro 系统完成

### MACRO-01. Macro namespace 与 runtime namespace 解耦

当前问题：

- top-level macro 仍会通过 `context.env.define(name, macro)` 发布到 runtime `Environment`。
- macro lookup 仍会 fallback 到 `env.resolve`。
- 这会让 compile-time namespace 和 runtime namespace 继续耦合。

要求：

- 设计独立的 compile-time macro namespace。
- 明确同名 runtime binding 与 macro binding 的优先级。
- 明确 macro 定义是否进入 runtime value namespace。

完成标准：

- macro 不再意外污染 runtime namespace。
- macro lookup 不再依赖普通 `Environment.resolve` 作为主路径。
- 对同名 macro/operator/value 有测试。

### MACRO-02. Module-level macro scope

当前问题：

- `macroexpand.py` 对 `module` 只是创建 body child scope。
- import/export 对 macro 的含义还没有建模。

要求：

- 明确模块内 macro 是否可导出。
- 明确 import macro 后是否参与调用方 compile-time expansion。
- 明确 macro export 与 runtime export 是否分离。

完成标准：

- module 内部 macro 可见性有测试。
- exported macro/imported macro 有测试。
- runtime export 与 compile-time export 不混淆。

### MACRO-03. Hygiene 策略

当前状态：

- 已有显式 `gensym`。
- 没有自动 hygiene。

建议阶段：

1. 保持显式 `gensym`。
2. 增加 symbol mark/rename。
3. 增加 intentional capture API。

完成标准：

- macro 内部临时变量不会捕获用户变量。
- 用户传入 symbol、macro 定义处 symbol、macro 生成 symbol 三类来源可区分。
- docs 说明 intentional capture 是否允许以及如何写。

### MACRO-04. Compile-time runtime

当前状态：

- macro body 已改用 `lower + IR VM`，这是正确方向。
- 但仍使用 runtime `Environment` 和一部分 evaluator 类型。

要求：

- 做 compile-time runtime facade。
- compile-time capability/effect 策略与 runtime 分开。
- macro body 执行不应再直接暴露完整 runtime 能力。

完成标准：

- `qy/macro.py` 不再需要从 `qy.evaluator` 获取 `Environment` 类型。
- macro expansion 的 effect/capability error 有稳定 diagnostics。
- compile-time 可用 operator 列表明确。

### MACRO-05. Source map 与 diagnostics

要求：

- source map 不只是 trace list，还要能回答“这个 expanded form 来自哪里”。
- diagnostics 同时能指向 macro call site 与 macro definition site。

完成标准：

- nested macro 出错时显示 expansion chain。
- LSP 可以消费 source map。

## P3：Evaluator 拆除

### EVAL-01. 拆出 runtime value 与 environment

当前 `evaluator.py` 仍是最大技术债。建议拆分：

- `qy/environment.py`
- `qy/operators.py`
- `qy/runtime_values.py`
- `qy/continuation.py`

完成标准：

- `Environment` 不再定义在 `evaluator.py`。
- `PureOperator`、`ControlOperator`、`MetaOperator` 等不再定义在 `evaluator.py`。
- `UserFunction`、`ComponentDefinition`、`QyContinuation` 不再定义在 `evaluator.py`。

### EVAL-02. 迁移 stdlib 对 evaluator 的依赖

当前 `qy/stdlib/core.py`、`strings.py`、`io.py`、`__init__.py` 仍直接依赖 evaluator。

要求：

- stdlib 只依赖 runtime value/environment/operator 模块。
- 旧 `evaluate_async/evaluate_body_async` 不应作为 stdlib 主路径。

完成标准：

- `rg "from qy.evaluator" qy/stdlib` 不再命中，或只命中明确 legacy shim。

### EVAL-03. Legacy evaluator 降级为 compatibility shim

要求：

- 旧 `evaluate/evaluate_source/evaluate_program` 可以暂时保留。
- 但实现应转调 `Qy` 或 IR VM，不再承担主执行逻辑。

完成标准：

- `evaluator.py` 文件规模明显下降。
- 新代码不再新增对 `evaluate_body_async` 的依赖。

## P4：Register VM 与 Bytecode 完整化

### VM-01. Bytecode backend 覆盖核心语言

下一批优先支持：

- `assert`
- `module`
- `from`
- `component`
- `eval`

再支持：

- `defeffect`
- `perform`
- `handle`
- `resume`

完成标准：

- bytecode backend 能跑现有主测试的大部分。
- 不支持的语义有明确 diagnostic，而不是运行时崩溃。

### VM-02. Operator metadata 接管 runtime dispatch

当前问题：

- `OperatorSignature` 已用于部分分析/lowering。
- runtime dispatch 仍大量依赖 Python class 与 fallback。

要求：

- metadata 统一描述：
  - signature
  - argument policy
  - return type
  - effects
  - compile-time/runtime availability
  - host fallback policy

完成标准：

- analyzer、lowering、MIR lowering、VM dispatch 读同一份 metadata。
- 自定义 operator 注册 API 要求声明 metadata，或者给出 conservative default。

### VM-03. Primitive opcode

当前 arithmetic/comparison 仍经 host-call path。

要求：

- 给最核心 primitive 增加 MIR/bytecode-native 表达。
- 先覆盖 `+ - * / eq < <= > >=`。

完成标准：

- benchmark 能比较 host-call 与 primitive opcode。
- bytecode VM 核心算术不依赖 Python operator object dispatch。

## P5：stdlib 与核心算子收敛

### CORE-01. 精简 core operator

长期核心建议只保留：

- quote/eval
- macro
- defun/lambda/let/cond
- arithmetic/comparison
- effect 基础
- module/import 基础

非核心数据结构算子迁移到命名空间：

- `py::list`
- `py::tuple`
- `py::dict`
- `py::set`
- string operators 也应移出 core。

完成标准：

- core operator 列表固定。
- stdlib module 和 core operator 边界清楚。
- tests 按 core/stdlib 分组。

## P6：性能、AOT、JIT、Python codegen

### PERF-01. Benchmark gate

要求：

- 当前 benchmark 已有 baseline。
- 下一步需要决定 CI 阈值和跳过策略。

完成标准：

- `make bench-check` 可作为 regression gate。
- bytecode unsupported case 会报告 skipped reason。
- baseline 更新必须在 `report.md` 解释。

### CODEGEN-01. Python codegen 原型

前置条件：

- MIR 覆盖核心语言。
- MIR verifier 完成。
- macro source map 更稳定。

要求：

- Python codegen 只消费 MIR。
- 不允许直接从 HIR 生成 Python。

完成标准：

- 能生成并运行简单 arithmetic/let/defun/cond。
- generated code 可关联 MIR dump 和 macro source map。

## 建议执行顺序

1. `P0-01`：建立 `report.md` 协作记录。
2. `P0-04`：增加 CLI 调试管线命令。
3. `MIR-02`：增加 MIR verifier。
4. `MIR-01`：补全 MIR 对 HIR 节点的覆盖和 diagnostics。
5. `MACRO-01`：macro namespace 与 runtime namespace 解耦。
6. `MACRO-02`：module-level macro scope。
7. `MACRO-04`：compile-time runtime facade。
8. `EVAL-01`：拆出 environment/operator/runtime value。
9. `VM-01`：bytecode backend 覆盖 `assert/module/from/component/eval`。
10. `MIR-03`：effect MIR/bytecode model。
11. `VM-03`：核心 primitive opcode。
12. `PERF-01`：benchmark gate。
13. `CODEGEN-01`：Python codegen 原型。
