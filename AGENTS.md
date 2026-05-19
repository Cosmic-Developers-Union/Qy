# AGENTS.md

本文件为 Codex 等编码代理提供本仓库的工作说明。沟通、说明文档和面向维护者的总结默认使用中文。

## 项目概览

QyLang 是 Python 实现的 like-Lisp 方言，核心是 algebraic effects + register VM。Python 是宿主，不是语言语义本体。

目标管线（固定）：

```text
source -> raw AST -> surface dialect -> macro expand -> HIR -> MIR -> LIR -> bytecode -> register VM
```

## 重要目录和文件

- `docs/package-structure.md`：目标包结构真源；新增目录、迁移旧 `.py` 文件、`stdlib -> std` 时先对齐这里。
- `qy/diag/`：统一诊断系统目标包，负责 diagnostic/reporter/fixit；迁移目标来自 `qy/diagnostics.py`。
- `qy/source/`：源码、Span、SourceMap、位置映射目标包；`SourceSpan` 后续迁入这里。
- `qy/session/`：编译会话、配置、feature flags、profile facts 目标包。
- `qy/build/`：build graph、artifact、cache、pipeline driver 目标包；只编排阶段，不实现阶段语义。
- `qy/project/`：`qy.toml`、package/module、项目依赖与 source roots 目标包。
- `qy/import_/`：import resolver/module loader 目标包；尾随下划线用于避开 Python 关键字。
- `qy/analysis/`：scope/ref/escape/liveness/effect analysis 目标包；迁移目标来自 `qy/analyzer.py`。
- `qy/debug/`：IR dump、trace、VM debug、LLVM command log 目标包。
- `qy/errors/`：语言级异常与内部编译器错误目标包；迁移目标来自 `qy/errors.py`。
- `qy/backend/vm/spec/`：VM target 规格目标包，负责 bytecode/opcode/ABI/state/effect protocol；不得依赖 Python VM instance。
- `qy/vm/`：VM 的 Python 实现目标包。
- `qy/vm/instance/`：VM 运行实例目标包，负责 machine/frame/state/scheduler/host adapter；只能实现 `qy/backend/vm/spec`。
- `qy/passes/`：按“阶段 + 主题”组织 pass；`pipeline.py` 调度，`pass_base.py` 定义接口，子目录包括 `raw/surface/macro/core/resolve/hir/closure/effect/control/mir/lir/optimize/emit`。
- `qy/reader.py`：基于 Lark 的 S-expression 读取器；目标 raw AST 只能由 `symbol` 与不可变 `chain` 组成，并提供 default surface dialect。当前代码把部分 literal 提前物化，属于待修偏移，不得当作目标模型。
- `qy/lowering.py`：Form → HIR（`qy/ir.py` 定义的 IR 节点）。
- `qy/ir.py`：HIR 数据结构（`CallExpr`、`LetExpr`、`HandleExpr`、`PerformExpr` 等）。
- `qy/mir.py`：MIR 数据结构，CFG / virtual register IR，含 effect opcode。
- `qy/mir_lowering.py`：HIR → MIR lowering。
- `qy/lir.py`：LIR 数据结构，线性化低层 IR。
- `qy/lir_lowering.py`：MIR → LIR lowering，CFG 展平，跳转 offset 解析。
- `qy/bytecode.py`：Bytecode 数据结构与 opcode 定义。
- `qy/bytecode_compiler.py`：LIR → BytecodeProgram，纯结构转换，不重新理解语义。
- `qy/register_vm.py`：唯一执行器（Register VM）。
- `qy/ir_vm/`：已删除；不得重新引入第二执行后端。
- `qy/environment.py`：`Environment`（symbol-space 实现）、`standard_environment`。
- `qy/operators.py`：`PureOperator`/`ScopeOperator`/`ControlOperator`/`EffectOperator`/`MetaOperator`（legacy dispatch）。
- `qy/runtime_values.py`：`EffectDefinition`、`UserFunction`、`HostObjectRef` 等 runtime 值类型。
- `qy/continuation.py`：`QyContinuation`，可恢复的效应续延。
- `qy/async_runtime.py`：`run_async` 同步/异步桥接（P1-3 兼容门面）。
- `qy/eval_runtime.py`：`evaluate_async` / `evaluate_body_async` / `evaluate_tail_body_async`（P1-3 兼容门面）。
- `qy/symbol_utils.py`：`ensure_symbol` 工具函数（P1-3 兼容门面）。
- `qy/evaluator.py`：legacy 求值器，仅通过 `eval_runtime.py` 受控导入；新代码不应从这里 import runtime 类型。
- `qy/runtime.py`：`Qy` 主类 API，串联完整 pipeline。
- `qy/analyzer.py`：静态分析、诊断、作用域和轻量类型检查。
- `qy/std/`：标准库目标包；新增标准能力应优先进入这里。
- `qy/stdlib/`：迁移期兼容目录；不得新增长期实现。当前 import 自 `async_runtime` / `eval_runtime` / `symbol_utils` 而非直接依赖 evaluator。
- `qy/cli.py`：Typer CLI，包括 `run`、`repl`、`ast`、`expand`、`hir`、`mir`、`lir`、`bytecode`、`fmt`、`check`、`typecheck`、`operators`、`lsp`。
- `tests/`：pytest 测试，基线 `uv run python -m pytest -q`。
- `examples/`：Qy 语言示例。
- `extensions/qylang-support-vscode/`：VS Code 语言支持扩展。
- `docs/ir-design.md`：HIR / MIR / LIR 的独立职责、禁止事项与 verifier 要求。

## 常用命令

依赖和命令优先使用 `uv`：

```bash
uv run python -m pytest tests/ -v --cov=qy --cov-report=term-missing
uv run python -m pytest tests/test_register_vm.py -v

uv run ruff check .
uv run ruff format .
uv run ty check .

uv run qy run examples/hello.qy
uv run qy hir examples/hello.qy
uv run qy mir examples/hello.qy
uv run qy lir examples/hello.qy
uv run qy bytecode examples/hello.qy
uv run qy repl
uv run qy ast examples/hello.qy

uv build
```

Makefile 中也有聚合命令：

```bash
make test
make lint
make lint-fix
make bench
make bench-check
```

## 代码约定

- Python 目标版本是 3.12，包管理使用 `uv`。
- Ruff 配置在 `pyproject.toml`，行宽 100。
- 导入风格由 Ruff/isort 管理，当前配置偏好单行导入。
- 禁止包内相对导入，使用 `from qy.xxx import ...`。
- 目标包结构见 `docs/package-structure.md`。不得长期同时保留同名 `name.py` 与 `name/`；旧 `.py` 文件迁移时先把 public API 搬入目标 package `__init__.py`，再删除旧文件。
- 标准库目标命名为 `qy.std`；`qy.stdlib` 只作为兼容迁移目录存在。
- 工程层包（`diag/source/session/build/project/import_/analysis/debug/errors`）只提供编译器基础设施，不得承载具体语言阶段语义。
- VM 必须区分 target spec 与 Python implementation：`qy/backend/vm/spec` 定义契约，`qy/vm` 实现该契约，`qy/vm/instance` 保存一次执行的可变状态；instance 不得定义 opcode/ABI 规格。
- 删除 legacy 文件前必须满足 `docs/package-structure.md` 的删除前置条件；不得让兼容 shim 无限期保留。
- 待删除源码必须使用 `QY_DELETE_AFTER_MIGRATION` 或 `QY_DELETE_AFTER_SEMANTIC_REPLACEMENT` 文件头标记，方便 `rg QY_DELETE_AFTER` 跟踪。
- `passes/` 只放变换和分析；`ir/` 只放数据结构；`backend/` 只放目标后端输出。
- 新核心语义必须落到明确 pipeline 阶段（surface dialect / macro expand / HIR / MIR / LIR / bytecode / VM），不能跨层补丁式扩散。
- HIR、MIR、LIR 不是同一 IR 的三种格式：
  - HIR 只保留高层语义 facts；
  - MIR 只表达 CFG / virtual register / explicit control-effect flow；
  - LIR 是 Qy abstract machine IR，负责 selection、layout、ABI、virtual stack、continuation frame、handler frame、symbol-space-chain transition、lookup operation、slot operation、fixup、peephole、debug injection；
  - 若一个变换无法归属到唯一一层，先修正边界再实现。
- 语法只有 S-expression；`form` 只是单个 S-expression 单元，不是第三类语法对象。reader 不得把 runtime value 提前塞进 raw AST。
- 新代码不得从 `qy.evaluator` import runtime 类型；应从 `qy.environment`、`qy.operators`、`qy.runtime_values`、`qy.continuation`、`qy.errors` import。库代码（stdlib 等）若需要评估函数应从 `qy.eval_runtime` 导入（P1-3 兼容门面）。
- bytecode compiler 不允许重新理解 HIR/MIR 语义；语义 lowering 必须经由 LIR。
- Qy 不保留可选 runtime backend；不得新增或维护 IR VM/evaluator backend 语义。公共执行入口必须走 register VM。
- 语言内核没有宿主环境；但标准实现总是围绕某个 `Qy` 实例展开，`pre-symbol-space-chain` 是该实例的初始查找链，reader、analyzer、LSP、lowering、runtime 都必须读取同一份实例事实。
- `pre-symbol-space-chain` 是链，不是单个特殊空间；standard profile、字面量空间、stdlib 空间、宿主注入空间都应以明确链节点建模。host reference/operator 必须通过实例链、显式注入或显式 import 进入 symbol-space-chain。
- runtime value 是 Qy 语义对象；Python value 只是当前实现或宿主互操作对象。两者不得混淆，跨宿主能力应通过 host reference / adapter 进入语言模型。
- chain 只负责 lookup；fold 才会把 binding 吸收到某个 symbol-space。`from` 是受 `exports` 约束的选择性 fold，module root 初始化也应使用同一模型。
- 语言核与默认 profile 分离；standard profile 可以预装 `+` 等常用算子，但这不把它们提升为核心 form。
- 新增 operator 前先判断能否由 Qy 自身实现；能写成 Qy library 的能力，不要下沉成 host operator。
- 用户自定义 operator 若需要被 analyzer / LSP 精确理解，创建者必须补充 arity、参数策略、参数/返回类型、effect 等声明；工具链不得凭实现细节猜测。
- `define` 只在当前 symbol-space 内一次性绑定，可以 shadow 链上后续 symbol-space 中的任意 symbol。
- 修改语言语义时，必须同步更新 `LANGUAGE.md` 与 `todo.md`。
- 修改 reader、lowering、evaluator、IR 或 analyzer 时，同步考虑 CLI、LSP、formatter 和测试覆盖。

## 测试策略

- 窄改动优先运行相关测试文件。
- 涉及 MIR/LIR/bytecode/VM 时运行：`uv run python -m pytest tests/test_mir.py tests/test_lir.py tests/test_register_vm.py tests/test_runtime.py -q`。
- 涉及 macro 时运行：`uv run python -m pytest tests/test_eval_macro.py tests/test_macroexpand.py tests/test_module_import.py -q`。
- 涉及 CLI 时运行 `tests/test_cli_commands.py`。
- 任何较大改动都要运行全量 `uv run python -m pytest -q` 和 `uv run ty check .`。

## 工作注意事项

- 当前仓库可能存在用户未提交改动；开始编辑前先看 `git status --short`，不要覆盖或回退非本次任务的修改。
- 文档或总结默认中文；代码标识符、公共 API、错误类型和命令保持英文原文。
- 不要把 `node_modules/`、`dist/`、`QyLang.egg-info/` 等生成物当作主要编辑目标。
- 如需新增操作符，新语义必须走 MIR/LIR/bytecode/VM，不能继续走 `PureOperator`/`ScopeOperator` 等 legacy dispatch。
- 如需新增 CLI 行为，保持 `qy FILE` 作为 `run` 快捷方式的现有语义。
- 每次完成工作后用一句话总结修改内容。
