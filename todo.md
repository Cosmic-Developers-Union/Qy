# Qy TODO

本文档记录接下来一段时间的工作规划。原则上后续先做 review、规划和架构收敛，避免继续无边界地扩展实现。

## 当前架构判断

当前系统已经具备完整编译管线的雏形：

```text
Form / Reader
  -> macroexpand
  -> HIR / ProgramIR
  -> MIR / CFG
  -> BytecodeProgram
  -> Register VM
```

我的判断：

- 方向是正确的。`ProgramIR -> MIR -> Bytecode` 这一层拆开后，后续 JIT/AOT/Python codegen 才有稳定输入。
- 当前最重要的不是继续加语法，而是把每层边界彻底稳定下来。
- `evaluator.py` 仍是最大技术债，它已经不再是主执行器，但还承担 runtime value、legacy operator、macro body execution 等职责。
- macro 系统已经比之前清晰，但仍不是最终形态。尤其是 hygiene、compile-time runtime、模块级 macro scope 还没有完全闭合。
- Register VM 已经能跑核心子集，但还不是完整语言 VM。它目前更像实验后端，需要逐步接管更多语义。

## 架构原则

- HIR 保留语言语义结构：`let`、`cond`、`defun`、`macro`、effect、module 等。
- MIR 表示控制流和虚拟寄存器，不再保留复杂结构化语法。
- Bytecode 只负责线性执行模型，不应该再理解 HIR。
- Register VM 只执行 bytecode，不应该直接处理 reader form 或 HIR。
- Macroexpand 必须在 HIR lowering 前完成，后端不应该理解用户宏。
- 用户自定义 operator 必须通过统一 metadata 描述签名、参数策略、effect 和阶段能力。

## 优先级 P0：先稳定结构

### 1. 固化 pipeline API

- 明确公开 API：
  - `read`
  - `macroexpand`
  - `lower`
  - `lower_mir`
  - `compile_bytecode`
  - `RegisterVirtualMachine`
- 给每层补最小文档，说明输入、输出、diagnostics 行为。
- 明确 `Qy.evaluate_source` 默认 backend 是否继续是 IR tree VM，bytecode backend 是否仍标记 experimental。

完成标准：

- README 或 docs 中有一张正式 pipeline 图。
- 每层 API 都有对应测试。
- `Qy(backend="bytecode")` 的限制被明确记录。

### 2. MIR 模型收敛

- 给 MIR 增加文档说明：
  - virtual register 不是 SSA。
  - `MIRBlock` 只允许 terminator 结束控制流。
  - `TAIL_CALL` 必须只出现在 terminator。
- 检查 MIR lowering 中 `cond/let/tail call` 的 CFG 是否有不可达块或多余 block。
- 增加 MIR dump/debug formatter，便于 review 和诊断。

完成标准：

- 能把 MIR 以可读文本打印出来。
- `tests/test_mir.py` 覆盖 `let`、`cond`、`defun`、`lambda`、macro definition、tail call。

## 优先级 P1：完成 macro 系统

### 3. Macro scope 与 module scope

- 当前 macro scope 已有局部作用域，但还需要审视 module/import/export 语义。
- 明确 top-level macro 是否默认 export。
- 明确 module 内 macro 的可见性：
  - 模块内部展开可见。
  - 是否允许导出 macro。
  - import macro 后是否参与调用方 compile-time expansion。

完成标准：

- 模块级 macro scope 有测试。
- from/import 对 macro 的行为明确。
- macro 不再意外污染 runtime value namespace。

### 4. Hygiene 设计

- 当前只有显式 `gensym`，不是自动 hygiene。
- 需要确定最终策略：
  - 第一阶段：继续显式 `gensym`。
  - 第二阶段：增加 mark/rename hygiene。
  - 第三阶段：支持 intentional capture API。
- 需要区分：
  - 用户传入 form 中的 symbol。
  - macro 定义处引入的 symbol。
  - macro expansion 新生成的 symbol。

完成标准：

- `gensym` 有完整测试。
- 有测试证明 macro 内部临时变量不会捕获用户变量。
- 有设计文档说明是否支持 intentional capture。

### 5. Compile-time effect 策略

- 当前默认 deny compile-time effect，这是正确的保守默认。
- 需要设计允许策略：
  - 哪些 effect 可以在 macro expansion 阶段执行。
  - 是否需要 capability。
  - 是否允许 IO。
  - 失败如何进入 diagnostics。
- 不建议直接复用 runtime effect handler，需要单独的 compile-time effect policy。

完成标准：

- `MacroExpansionOptions(effect_policy=...)` 行为稳定。
- compile-time effect error 有 source span 和 expansion trace。
- docs 中明确默认策略。

### 6. Macro expansion trace/source map

- 现有 trace 已记录 macro、span、generated symbols。
- 下一步需要完善 source map：
  - expanded form 到原始 form 的映射。
  - nested macro expansion trace。
  - diagnostics 能指回 macro call site 和 macro definition site。

完成标准：

- macro expansion error 能显示 call site。
- nested macro trace 有测试。
- source map 可被 LSP 使用。

## 优先级 P2：逐步移除 evaluator

### 7. 拆出 runtime value 模块

当前 `evaluator.py` 仍包含：

- `Environment`
- operator classes
- `UserFunction`
- `ComponentDefinition`
- `QyContinuation`
- legacy AST evaluator helpers

建议拆分：

- `qy/environment.py`
- `qy/operators.py`
- `qy/runtime_values.py`
- `qy/continuation.py`

完成标准：

- `evaluator.py` 不再定义核心 runtime value。
- legacy AST evaluator 被明确标记为 compatibility 或删除。
- import graph 不再让 macro/VM 反向依赖 evaluator。

### 8. Macro body execution 脱离 evaluator

- 当前 `MacroDefinition.expand` 仍通过 `evaluate_body_async` 执行 macro body。
- 这意味着 macro 系统仍依赖 legacy evaluator facade。
- 需要决定 macro body 的执行后端：
  - 用 IR VM 执行 compile-time body。
  - 用 bytecode VM 执行 compile-time body。
  - 单独实现 compile-time evaluator。

我的建议：

- 短期使用 IR VM 执行 macro body。
- 中期做 compile-time runtime facade。
- 长期 compile-time 和 runtime 共享 bytecode VM，但 capability/effect 策略分开。

完成标准：

- `qy/macro.py` 不再 import `evaluate_body_async`。
- macro expansion 不依赖 `evaluator.py`。

## 优先级 P3：Register VM 完整化

### 9. Bytecode backend 覆盖更多语义

当前 bytecode backend 支持核心子集。下一步逐项补：

- `assert`
- `component`
- `module`
- `from`
- `eval`
- `perform`
- `handle`
- `resume`
- `defeffect`

完成标准：

- bytecode backend 能跑现有主测试的大部分。
- 不支持的语义有明确 diagnostics，而不是运行时崩溃。

### 10. Effect 在 MIR/bytecode 中建模

effect 不应该长期停留在 legacy operator fallback。

需要设计：

- MIR terminator 或 instruction 表示 `perform`。
- handler stack 是否作为 VM frame 状态。
- continuation 如何编码。
- `resume` 是否是特殊 instruction。

完成标准：

- `perform/handle/resume` 有 MIR 表达。
- Register VM 能跑现有 effect 测试子集。

### 11. Operator metadata 统一 runtime dispatch

当前 `OperatorSignature` 已经存在，但 runtime dispatch 仍没有完全被 metadata 接管。

需要统一：

- signature
- argument policy
- return type
- effects
- compile-time/runtime availability
- host fallback policy

完成标准：

- analyzer、HIR lowering、MIR lowering、runtime dispatch 都读同一份 metadata。
- 自定义 operator 的注册 API 要求明确声明 metadata，或者有默认 conservative metadata。

## 优先级 P4：stdlib 与核心算子收敛

### 12. 精简核心算子

长期目标是核心算子最小化。建议保留：

- arithmetic/comparison
- quote/eval
- macro
- defun/lambda/let/cond
- effect 基础
- module/import 基础

非核心数据结构算子后续迁移到命名空间：

- `py::list`
- `py::tuple`
- `py::dict`
- `py::set`
- string operators 也应移出 core。

完成标准：

- core operator 列表明确。
- stdlib module 和 core operator 边界清楚。
- tests 按 core/stdlib 分组。

### 13. Legacy operator IR-native 化

- 当前很多 stdlib operator 仍通过 host Python callable。
- 需要区分：
  - primitive operator
  - host operator
  - macro operator
  - effect operator
- 核心 primitive 应该有 MIR/bytecode-native 实现。

完成标准：

- arithmetic/comparison 不再依赖 host-call path。
- benchmark 能比较 host-call 和 primitive-call。

## 优先级 P5：性能与后端

### 14. Benchmark 扩展

当前 benchmark 有：

- source
- lower
- ir

需要加入：

- macroexpand
- HIR lower
- MIR lower
- bytecode compile
- bytecode VM

完成标准：

- benchmark 能比较 IR VM 和 Register VM。
- baseline gate 包含 bytecode backend。

### 15. Python codegen / AOT / JIT

不要在 MIR 稳定前推进 codegen。

未来顺序：

1. MIR interpreter/debug runner。
2. MIR -> bytecode 稳定。
3. MIR -> Python codegen。
4. bytecode/JIT 或 native backend。

完成标准：

- Python codegen 只消费 MIR，不直接消费 HIR。
- codegen source map 能关联 macro expansion trace。

## 当前不要做的事

- 不要继续无边界加新语法。
- 不要让 bytecode compiler 重新理解 HIR。
- 不要让 macro 系统继续依赖更多 evaluator helper。
- 不要急着删除 IR VM；它现在仍是完整语义的稳定参考实现。
- 不要先做 SSA。当前 virtual register MIR 足够支撑 register VM 和 codegen 原型。

## 建议的下一步执行顺序

1. 给 MIR 加 dump/debug formatter。
2. 给 pipeline 写 docs。
3. 完成 macro module scope/import/export 语义。
4. 让 macro body execution 脱离 `evaluator.py`。
5. 扩展 bytecode backend 支持 `assert/component/module/from`。
6. 设计并实现 MIR effect/handler 模型。
7. 扩展 benchmark 到 MIR/bytecode。
8. 开始 Python codegen 原型。
