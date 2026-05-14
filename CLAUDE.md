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
source -> ast -> expand -> HIR -> MIR -> LIR -> bytecode -> register VM
```

### 核心组件

- **Reader** (`reader.py`) — 基于 Lark 的 S-expression 解析器，源码 → `Symbol`/tuple Form 对象（syntax datum），带源码位置追踪
- **Lowering** (`lowering.py`) — Form → HIR，解析符号绑定，构建作用域层次
- **HIR** (`ir.py`) — 高层语义 IR 数据结构（`CallExpr`、`LetExpr`、`HandleExpr`、`PerformExpr` 等）
- **MIR** (`mir.py`) — CFG / virtual register IR，控制流显式，含 `PERFORM`/`HANDLE`/`RESUME`
- **LIR** (`lir.py`, `lir_lowering.py`) — 线性化低层 IR，CFG 展平，跳转目标解析为 offset
- **Bytecode compiler** (`bytecode_compiler.py`) — LIR → `BytecodeProgram`，纯结构转换，不重新理解语义
- **Register VM** (`register_vm.py`) — 主执行器，最终执行目标
- **IR VM** (`ir_vm/`) — reference/compatibility runtime，不是最终执行路径
- **Analyzer** (`analyzer.py`) — 静态分析，类型推断、作用域追踪、参数数量检查
- **Runtime** (`runtime.py`) — `Qy` 主类 API，串联完整 pipeline
- **Environment** (`environment.py`) — symbol-space 实现，`standard_environment`
- **Operators** (`operators.py`) — `PureOperator`/`ScopeOperator`/`ControlOperator`/`EffectOperator`/`MetaOperator`（legacy dispatch，新语义不走这里）
- **Stdlib** (`stdlib/`) — 内置操作符，`core.py` 只注册最小核心

### 执行器优先级

| 执行器           | 状态                                  |
| ---------------- | ------------------------------------- |
| `register_vm.py` | 主执行器，新语义目标                  |
| `ir_vm/`         | reference/compatibility，不增加新语义 |
| `evaluator.py`   | legacy，向后兼容 facade               |

### 效应系统

代数效应通过 `defeffect`/`perform`/`handle`/`resume` 实现。`QyContinuation` 是可恢复的效应续延。效应在 MIR 层有独立 opcode，LIR/bytecode/register VM 中有对应支持。

### 值类型（values.py）

`QyNil`、`QyT`（单例）、`QyChain`/`QyCons`（链表），Python 原生类型直接互操作（host value）。

## 技术栈

- Python >=3.12，使用 `uv` 管理依赖
- 依赖：lark（解析）、typer（CLI）、pygls（LSP）
- 工具：ruff（lint+format）、ty（类型检查）、pytest（测试）、commitlint（提交信息）
- VSCode 扩展：`extensions/qylang-support-vscode/`
