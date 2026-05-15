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

- **Reader** (`reader.py`) — 基于 Lark 的 S-expression 解析器，源码 → raw `Symbol`/tuple Form 对象（syntax datum），带源码位置追踪；默认 read pipeline 额外执行 default surface dialect
- **Lowering** (`lowering.py`) — Form → HIR，解析符号绑定，构建作用域层次
- **HIR** (`ir.py`) — 高层语义 IR 数据结构（`CallExpr`、`LetExpr`、`HandleExpr`、`PerformExpr` 等）
- **MIR** (`mir.py`) — CFG / virtual register IR，控制流显式，含 `PERFORM`/`HANDLE`/`RESUME`
- **LIR** (`lir.py`, `lir_lowering.py`) — 线性化低层 IR，CFG 展平，跳转目标解析为 offset
- **Bytecode compiler** (`bytecode_compiler.py`) — LIR → `BytecodeProgram`，纯结构转换，不重新理解语义
- **Register VM** (`register_vm.py`) — 唯一执行器
- **IR VM** (`ir_vm/`) — 迁移待删代码；不能作为 reference backend 或新语义承载点
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
| `ir_vm/`         | 迁移待删，不能新增语义                                    |
| `evaluator.py`   | legacy，迁移待删；仅通过 `eval_runtime.py` 受控导入       |

Qy 不保留 `backend` 选择；公共执行入口必须走 register VM。语言内核没有宿主环境；Qy 实例可配置 pre-symbol-space，默认实现可惰性预定义数字/字符串等传统符号。Python host interop 不属于默认语言核心；host value/operator 必须通过实例 pre-symbol-space、显式注入或显式 import 进入 symbol-space-chain。`define` 只检查当前 symbol-space，可以 shadow parent。

### 效应系统

代数效应通过 `defeffect`/`perform`/`handle`/`resume` 实现。`QyContinuation` 是可恢复的效应续延。效应在 MIR 层有独立 opcode，LIR/bytecode/register VM 中有对应支持。

**Effect Frame**：在 register VM 中，当 `PERFORM` 指令执行时，当前帧的状态（registers、env、pc、parents、results、function_value、function）被显式捕获为 `_EffectFrame` 冻结数据类，而非分散的 Python 变量。这为后续迁移到 LIR 级别的 effect frame 表达做准备。

### 值类型（values.py）

`QyNil`、`QyT`（单例）、`QyChain`/`QyCons`（链表），Python 原生类型直接互操作（host value）。

## 技术栈

- Python >=3.12，使用 `uv` 管理依赖
- 依赖：lark（解析）、typer（CLI）、pygls（LSP）
- 工具：ruff（lint+format）、ty（类型检查）、pytest（测试）、commitlint（提交信息）
- VSCode 扩展：`extensions/qylang-support-vscode/`
