# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

QyLang 是 Python 实现的 like-Lisp 语言，核心是 algebraic effects + register VM。Python 是宿主，不是语言语义本体。使用中文进行沟通。

## 常用命令

```bash
# 运行测试（全部）
uv run python -m pytest tests/ -v --cov=qy --cov-report=term-missing

# 运行单个测试文件
uv run python -m pytest tests/test_register_vm.py -v

# 运行单个测试用例
uv run python -m pytest tests/test_register_vm.py::test_arithmetic -v

# Lint
uv run ruff check .
uv run ruff format .
uv run ty check .

# Lint 自动修复
uv run ruff check . --fix --unsafe-fixes && uv run ruff format .

# 运行 CLI
uv run qy run examples/hello.qy
uv run qy repl
uv run qy ast examples/hello.qy
uv run qy hir examples/hello.qy
uv run qy mir examples/hello.qy
uv run qy lir examples/hello.qy
uv run qy bytecode examples/hello.qy

# 构建
uv build
```

## 架构

目标管线（固定，不可变）：

```text
source -> raw AST -> surface dialect -> macro expand -> HIR -> MIR -> LIR -> bytecode -> register VM
```

### 核心组件

- **Reader** (`reader.py`) — 基于 Lark 的 S-expression 解析器；目标 raw AST 只能由 `symbol` 与不可变 `chain` 组成，带源码位置追踪；默认 read pipeline 额外执行 default surface dialect。当前代码里把部分 literal 提前物化，属于待修偏移
- **Lowering** (`lowering.py`) — Form → HIR，解析符号绑定，构建作用域层次
- **HIR** (`ir.py`) — 高层语义 IR；只保留 resolved binding、structured control、operator/effect/module facts
- **MIR** (`mir.py`) — CFG / virtual register IR；控制流、tail call、effect flow 显式
- **LIR** (`lir.py`, `lir_lowering.py`) — Qy abstract machine IR；负责 instruction selection、layout、ABI、virtual stack、continuation frame、handler frame、symbol-space-chain transition、lookup operation、slot operation、fixup、peephole、debug injection
- **Bytecode compiler** (`bytecode_compiler.py`) — LIR → `BytecodeProgram`，纯结构转换，不重新理解语义
- **Register VM** (`register_vm.py`) — 唯一执行器
- **IR VM** (`ir_vm/`) — 已删除；不得重新引入第二执行后端
- **Analyzer** (`analyzer.py`) — 静态分析，类型推断、作用域追踪、参数数量检查
- **Runtime** (`runtime.py`) — `Qy` 主类 API，串联完整 pipeline
- **Environment** (`environment.py`) — symbol-space 实现，`standard_environment`
- **Operators** (`operators.py`) — `PureOperator`/`ScopeOperator`/`ControlOperator`/`EffectOperator`/`MetaOperator`（legacy dispatch，新语义不走这里）
- **Runtime Values** (`runtime_values.py`) — `UserFunction`、`EffectDefinition`、`HostObjectRef` 等 runtime 值类型
- **Continuation** (`continuation.py`) — `QyContinuation`，可恢复的效应续延
- **Compatibility Facades** (新) — 为迁移期间的兼容性提供：
  - `async_runtime.py`：`run_async` 同步/异步桥接，从 evaluator 抽离
  - `eval_runtime.py`：`evaluate_async` / `evaluate_body_async` / `evaluate_tail_body_async`，stdlib 用兼容门面
  - `symbol_utils.py`：`ensure_symbol` 工具函数
- **Stdlib** (`stdlib/`) — 内置操作符，`core.py` 只注册最小核心；import 自 `async_runtime` / `eval_runtime` / `symbol_utils` 而非直接依赖 evaluator

### 执行器约束

| 执行器           | 状态                                                      |
| ---------------- | --------------------------------------------------------- |
| `register_vm.py` | 唯一执行器，新语义目标；使用 \_EffectFrame 显式表达效应帧 |
| `ir_vm/`         | 已删除，不能重新引入第二执行后端                          |
| `evaluator.py`   | legacy，迁移待删；仅通过 `eval_runtime.py` 受控导入       |

Qy 不保留 `backend` 选择；公共执行入口必须走 register VM。语言内核没有宿主环境；但标准实现总是围绕某个 `Qy` 实例展开，`pre-symbol-space-chain` 是该实例的初始查找链，reader、analyzer、LSP、lowering、runtime 都必须读取同一份实例事实。它是链，不是单个特殊空间；standard profile、字面量空间、stdlib 空间、宿主注入空间都可以占据链上的明确位置。chain 只提供 lookup；fold 才会把 binding 吸收到某个 symbol-space。module root 初始化与 `from` 必须共用这套 fold 模型，后者是受 `exports` 约束的选择性 fold。语言核与默认 profile 分离，profile 可以预装 `+` 等常用算子，但这不把它们提升为核心 form。Python host interop 不属于默认语言核心；host value/operator 必须通过实例链、显式注入或显式 import 进入 symbol-space-chain。`define` 只检查当前 symbol-space，可以 shadow 后续链节点。

语法只有 S-expression；`form` 只是单个 S-expression 单元，不是第三类语法对象。reader 只能做源码到 `symbol` / `chain` 的映射，不得提前引入 runtime value。HIR / MIR / LIR 必须彼此独立：HIR 不得含 CFG/寄存器，MIR 不得含 Environment/物理布局，LIR 不得只是 bytecode opcode 的别名层，并且必须显式建模 virtual stack、continuation、handler、ss-chain transition、lookup 与 slot operation。详细边界见 `docs/ir-design.md`。

### 效应系统

代数效应通过 `defeffect`/`perform`/`handle`/`resume` 实现。`QyContinuation` 是可恢复的效应续延。效应在 MIR 层有独立 opcode，LIR/bytecode/register VM 中有对应支持。

**Effect/Continuation Frame**：当前 `_EffectFrame` 是过渡实现。目标模型中 `handle`/`perform`/`resume` 必须在 LIR 降成 virtual stack、continuation frame、handler frame 与 ss-chain transition；bytecode/VM 只执行这些低层机制，不再保留语言级 `PERFORM`/`HANDLE` 语义。

### 值类型（values.py）

`QyNil`、`QyT`（单例）、`QyChain`/`QyCons`（链表），Python 原生类型直接互操作（host value）。

## 技术栈

- Python >=3.12，使用 `uv` 管理依赖
- 依赖：lark（解析）、typer（CLI）、pygls（LSP）
- 工具：ruff（lint+format）、ty（类型检查）、pytest（测试）、commitlint（提交信息）
- VSCode 扩展：`extensions/qylang-support-vscode/`
