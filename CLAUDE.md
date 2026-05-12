# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

QyLang 是一个用 Python 实现的符号化 Lisp 语言，核心特性包括：代数效应（algebraic effects）系统、async-first 运行时、Python 互操作。使用中文进行沟通。

## 常用命令

```bash
# 运行测试（全部）
uv run python -m pytest tests/ -v --cov=qy --cov-report=term-missing

# 运行单个测试文件
uv run python -m pytest tests/test_evaluator.py -v

# 运行单个测试用例
uv run python -m pytest tests/test_evaluator.py::test_arithmetic -v

# Lint
uv run ruff check .
uv run ruff format .
uv run ty check .

# Lint 自动修复
uv run ruff check . --fix --unsafe-fixes && uv run ruff format .

# 运行 CLI
uv run qy run examples/hello.qy
uv run qy repl
uv run qy check examples/hello.qy
uv run qy ast examples/hello.qy

# 构建
uv build
```

## 架构

数据流管线：`Source → Reader → Forms → Lowering → IR → Evaluator → Values`

### 核心组件

- **Reader** (`reader.py`) — 基于 Lark 的 S-expression 解析器，源码 → `Symbol`/tuple Form 对象，带源码位置追踪
- **Lowering** (`lowering.py`) — Form → 类型化 IR 表达式，解析符号绑定，构建作用域层次
- **IR** (`ir.py`) — 中间表示数据结构（`CallExpr`、`LiteralExpr`、`LetExpr`、`HandleExpr`、`PerformExpr` 等）
- **Evaluator** (`evaluator.py`) — 异步效应式求值引擎，核心求值逻辑
- **Analyzer** (`analyzer.py`) — 静态分析，类型推断、作用域追踪、参数数量检查
- **Runtime** (`runtime.py`) — `Qy` 主类 API，串联读取/降低/求值流程
- **Stdlib** (`stdlib/`) — 内置操作符：`core.py`（算术、控制流、defun/lambda/let/component/module/macro）、`strings.py`、`io.py`、`imports.py`、`module.py`

### 操作符分类（evaluator.py 中定义）

| 类型 | 说明 | 示例 |
| --- | --- | --- |
| `PureOperator` | 急切求值参数 | `+`, `*`, `list` |
| `ScopeOperator` | 接收环境 | `defun`, `lambda`, `let`, `component`, `module` |
| `ControlOperator` | 控制求值流程 | `cond`, `handle` |
| `EffectOperator` | 效应处理 | `perform`, `resume`, `assert`, `await`, `py` |
| `MetaOperator` | 接收原始语法树 | `quote`, `eval`, `macro` |

### 效应系统

代数效应通过 `perform`/`handle`/`resume` 实现。`QyContinuation` 是可恢复的效应续延。内置效应包括 `assert-failed`、`python-error`。效应用 `defeffect` 声明。

### 值类型（values.py）

`QyNil`、`QyT`（单例）、`QyChain`/`QyCons`（链表），Python 原生类型直接互操作。

## 技术栈

- Python >=3.12，使用 `uv` 管理依赖
- 依赖：lark（解析）、typer（CLI）、pygls（LSP）
- 工具：ruff（lint+format）、ty（类型检查）、pytest（测试）、commitlint（提交信息）
- VSCode 扩展：`extensions/qylang-support-vscode/`
