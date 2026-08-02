# 协作文件

## 项目概览

QyLang 是一个用 Python 实现的符号化 Lisp 方言。仓库主体是 `qy/` Python 包，配套包含 CLI、LSP、标准库、示例程序、测试，以及一个 VS Code 扩展。

重要目录和文件：

- `qy/frontend/`：基于 Lark 的 S-expression 读取器、surface dialect、CST 解析、`Symbol` / `Form`。
- `qy/macro/`：macro 展开、hygiene、trace、compile-time namespace；compile-time 求值已脱离 bytecode / register VM。
- `qy/passes/`：按"阶段 + 主题"组织的 pass；`pipeline.py` 调度，`pass_base.py` 定义接口。
- `qy/core/`：symbol / chain / binding slot / operator declaration / effect declaration。
- `qy/sem/`：runtime value 模型（`core.py`）与可执行 runtime value（`runtime.py`：`UserFunction` / `ComponentOperator` / `BytecodeFunctionValue` / `EffectDefinition`）。
- `qy/ir/`：HIR / MIR / LIR 三个独立 IR 子包。
- `qy/backend/vm/`：VM target — bytecode emit / verifier / 优化；`spec/` 子包是稳定契约。
- `qy/vm/` + `qy/vm/instance/`：register VM 的 Python 实现 + 单次执行的可变实例。
- `qy/build/`：pipeline driver；只编排阶段，不实现阶段语义。
- `qy/runtime.py`：`Qy` / `AsyncQy` 主类 API，串联完整管线。
- `qy/std/`：标准库目标包。
- `qy/stdlib/`：迁移期兼容 shim（仅 `__init__.py`）；不得新增长期实现。
- `qy/cli/`：Typer CLI，包含 `run`、`repl`、`fmt`、`ast`、`expand`、`hir`、`mir`、`lir`、`bytecode`、`check`、`typecheck`、`operators`、`lsp`、`completion`、`export`、`llvm`、`pkg`。
- `tests/`：pytest 测试，基线 `uv run python -m pytest -q`。
- `examples/`：Qy 语言示例（`validation/`、`design/`、`host/`）。
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

uv run qy run examples/hello.qy
uv run qy ast examples/hello.qy
uv run qy expand examples/hello.qy
uv run qy hir examples/hello.qy
uv run qy mir examples/hello.qy
uv run qy lir examples/hello.qy
uv run qy bytecode examples/hello.qy
uv run qy repl

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
- 尽量保持当前小核心结构，新增行为优先接入现有 `RuntimeSpace` / 操作符 / IR / 诊断 / 标准库机制。
- 修改 reader、lowering、IR 或 analyzer 时，要同步考虑 CLI、LSP、formatter 和测试覆盖。
- 公共 Python API 入口：`Qy` / `AsyncQy`、`compile_source_to_bytecode` / `compile_source_to_kind`（`qy.build.pipeline`）、`RegisterVirtualMachine`（`qy.vm.instance.machine`）。**已移除**的入口：`Qy.macroexpand_source`、`Qy.lower`、`Qy.lower_mir`、`Qy.compile_bytecode`、`Qy.evaluate_ir`、`qy.ir_vm.*`、`qy.evaluator`、`Qy(backend=...)`。
- Qy 源码示例和测试应保持可读，避免只为实现方便而改变语言表层语义。

## 测试策略

- 窄改动优先运行相关测试文件，例如 `uv run python -m pytest tests/test_reader_forms.py -v`。
- 涉及求值、作用域、操作符、异步、效应或 IR 时，至少运行相关测试，并在可行时运行全量 `make test`。
- 涉及 CLI 时运行 `tests/test_cli_commands.py`、`tests/test_qytest_runner.py`、`tests/test_cli_repl.py` 或对应测试。
- 涉及格式化时运行 `tests/test_formatter.py`。
- 涉及 LSP 时运行 `tests/test_lsp.py`。

## 工作注意事项

- 当前仓库可能存在用户未提交改动；开始编辑前先看 `git status --short`，不要覆盖或回退非本次任务的修改。
- 文档或总结默认中文；代码标识符、公共 API、错误类型和命令保持英文原文。
- 不要把 `node_modules/`、`dist/`、`QyLang.egg-info/` 等生成物当作主要编辑目标。
- 如需新增操作符，优先补齐操作符签名、文档输出、分析器诊断和最小测试。
- **CLI 隐式重定向**：`qy FILE` 隐式走 `qy run FILE` 在 typer 0.26.8 / click 8.4.2 下不再生效（`qy/cli/__init__.py` 的 `QyGroup.resolve_command` 已是 dead code），请始终用显式 `qy run FILE` 形式。详见 `AGENTS.md` 与 `qy/cli/__init__.py`。

## 特别注意

- 如果要求你完成 todo.md 中的工作，请按优先级分批推进，不要试图在单个会话内推完 Phase B / C / D / E 等大段语义层工作（每个 phase 都涉及设计决策与多文件重构）。当前已完成：Phase A0 包结构收口、Category 1 cache 清理、2 个 CLI 入口测试修复、`QyGroup` cwd fallback 文档化。剩余主线在 `todo.md` Phase B / C / D / E。