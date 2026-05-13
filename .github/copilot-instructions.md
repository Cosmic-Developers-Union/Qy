# 协作文件

## 项目概览

QyLang 是一个用 Python 实现的符号化 Lisp 方言。仓库主体是 `qy/` Python 包，配套包含 CLI、LSP、标准库、示例程序、测试，以及一个 VS Code 扩展。

重要目录和文件：

- `qy/reader.py`：基于 Lark 的 S-expression 读取器，生成 `Symbol`、tuple 等 Form。
- `qy/lowering.py`：将 Form 降低到 `qy/ir.py` 中定义的 IR。
- `qy/evaluator.py`：符号表达式求值器、环境、操作符类型、异步与效应运行逻辑。
- `qy/ir_vm.py`：IR 执行入口。
- `qy/runtime.py`：`Qy` 对外 API，串联读取、降低、求值和注册操作符。
- `qy/analyzer.py`：静态分析、诊断、作用域和轻量类型检查。
- `qy/stdlib/`：内置标准库操作符和模块导入支持。
- `qy/cli.py`：Typer CLI，包括 `run`、`repl`、`fmt`、`ast`、`check`、`typecheck`、`operators`、`lsp`、`completion`。
- `tests/`：pytest 测试。
- `examples/`：Qy 语言示例。
- `extensions/qylang-support-vscode/`：VS Code 语言支持扩展。

## 常用命令

依赖和命令优先使用 `uv`：

```bash
uv run python -m pytest tests/ -v --cov=qy --cov-report=term-missing
uv run python -m pytest tests/test_runtime.py -v
uv run python -m pytest tests/test_runtime.py::test_qy_instance_registers_external_operators -v

uv run ruff check .
uv run ruff format .
uv run ty check .

uv run qy run examples/codes/code001.qy
uv run qy examples/codes/code001.qy
uv run qy repl
uv run qy fmt examples/codes/code001.qy
uv run qy check examples/codes/code001.qy
uv run qy ast examples/codes/code001.qy
uv run qy operators

uv build
```

Makefile 中也有聚合命令：

```bash
make test
make lint
make lint-fix
make build
```

注意：`make lint` 会运行 `ruff format .`，会修改格式；只想检查时先单独运行 `uv run ruff check .` 和 `uv run ty check .`。

## 代码约定

- Python 目标版本是 3.12，包管理使用 `uv`。
- Ruff 配置在 `pyproject.toml`，行宽 100。
- 导入风格由 Ruff/isort 管理，当前配置偏好单行导入。
- 禁止包内相对导入，使用 `from qy.xxx import ...`。
- 尽量保持当前小核心结构，新增行为优先接入现有 `Environment`、操作符、IR、诊断和标准库机制。
- 修改 reader、lowering、evaluator、IR 或 analyzer 时，要同步考虑 CLI、LSP、formatter 和测试覆盖。
- Qy 源码示例和测试应保持可读，避免只为实现方便而改变语言表层语义。

## 测试策略

- 窄改动优先运行相关测试文件，例如 `uv run python -m pytest tests/test_reader_forms.py -v`。
- 涉及求值、作用域、操作符、异步、效应或 IR 时，至少运行相关测试，并在可行时运行全量 `make test`。
- 涉及 CLI 时运行 `tests/test_cli_commands.py`、`tests/test_cli_repl.py` 或对应测试。
- 涉及格式化时运行 `tests/test_formatter.py`。
- 涉及 LSP 时运行 `tests/test_lsp.py`。

## 工作注意事项

- 当前仓库可能存在用户未提交改动；开始编辑前先看 `git status --short`，不要覆盖或回退非本次任务的修改。
- 文档或总结默认中文；代码标识符、公共 API、错误类型和命令保持英文原文。
- 不要把 `node_modules/`、`dist/`、`QyLang.egg-info/` 等生成物当作主要编辑目标。
- 如需新增操作符，优先补齐操作符签名、文档输出、分析器诊断和最小测试。
- 如需新增 CLI 行为，保持 `qy FILE` 作为 `run` 快捷方式的现有语义。

## 特别注意

- 如果要求你完成 todo.md 中的工作, 请按照 todo.md 中的要求, **全部**完成.
