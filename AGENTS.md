# AGENTS.md

本文件为 Codex 等编码代理提供本仓库的工作说明。沟通、说明文档和面向维护者的总结默认使用中文。

## 项目概览

QyLang 是 Python 实现的 like-Lisp 方言，核心是 algebraic effects + register VM。Python 是宿主，不是语言语义本体。

目标管线（固定）：

```text
source -> raw AST -> surface dialect -> macro expand -> HIR -> MIR -> LIR -> bytecode -> register VM
```

## 重要目录和文件

### 编译器基础设施（compiler infrastructure）

- `docs/package-structure.md`：目标包结构真源；新增目录、迁移旧 `.py` 文件、`stdlib -> std` 时先对齐这里。
- `qy/diag/`：统一诊断系统（`diagnostic.py`、`reporter.py`、`fixit.py`）。
- `qy/source/`：源码位置（`file.py`、`span.py`、`sourcemap.py`）。
- `qy/session/`：编译会话、配置、feature flags、profile facts（`config.py`、`context.py`、`runtime_space.py`、`pre_ss.py`、`profile.py`、`number_ops.py`）。
- `qy/build/`：pipeline driver、artifact、cache、build graph（`pipeline.py`、`artifact.py`、`cache.py`、`graph.py`、`driver.py`）。
- `qy/project/`：`qy.toml`、package/module、项目依赖与 source roots。
- `qy/import_/`：import resolver/module loader/from-fold bridge；尾随下划线用于避开 Python 关键字。
- `qy/analysis/`：liveness analysis（scope/ref/escape/effect 分析已收敛到 canonical frontend + HIR verifier，旧 `infer.py`/`scope.py`/`refs.py`/`escape.py`/`effects.py` 已删除）。
- `qy/debug/`：IR dump、trace、VM debug、LLVM command log。
- `qy/errors/`：语言级异常、runtime error、compile error、internal compiler error 分类。

### 语言内核与管线（language pipeline）

- `qy/frontend/`：基于 Lark 的 S-expression 读取器（CST / reader_macro / surface dialect / Form 与 Symbol）。目标 raw AST 只能由 `symbol` 与不可变 `chain` 组成；当前代码把部分 literal 提前物化属于待修偏移，不得当作目标模型。
- `qy/macro/`：macro expand / hygiene / trace / compile-time namespace；不得依赖 bytecode / register VM 执行宏体。
- `qy/core/`：symbol、immutable chain、binding slot、operator/effect declaration、operator signature 模型。**不得**混入 profile / compat 便利算子。
- `qy/sem/`：面向 VM / backend 的 runtime value 模型与抽象机语义（`core.py` 定义 value 类型，`runtime.py` 定义可执行 runtime value：`EffectDefinition` / `UserFunction` / `ComponentOperator` / `BytecodeFunctionValue`）。
- `qy/ir/`：HIR / MIR / LIR 三个独立的 IR 子包；只放数据结构。
  - `qy/ir/hir/`：高层语义 IR，含 `ProgramIR`、`CallExpr`、`LiteralExpr`、`Binding` 等。
  - `qy/ir/mir/`：CFG + virtual register IR，含 `MIRProgram` / `MIRFunction` / `MIRBlock` / `MIRInstruction` / `MIRTerminator` 与 `verify_mir`。
  - `qy/ir/lir/`：Qy abstract-machine IR，含 `LIRProgram` / `LIRFunction` / `LIRInstruction` / `LIRFrameLayout` / `LIRContinuationLayout` / `LIRHandlerLayout` / `LIRBindingAddr` 与 `verify_lir`（symbol-space layout 复用中性类型 `qy.ir.layout.SymbolSpaceLayout`，不再有 LIR 专属 layout 类型）。
- `qy/passes/`：按"阶段 + 主题"组织 pass。`pipeline.py` 是调度器，`pass_base.py` 定义 `Pass` / `PassContext` / `PassResult`。子目录：`raw/surface/macro/core/resolve/hir/closure/effect/control/mir/lir/optimize/emit`。**只放变换和分析，不放 IR 数据结构。**
- `qy/backend/`：目标后端输出。
  - `qy/backend/vm/`：register VM target — bytecode emit / verifier；**不是第二 runtime backend**。
  - `qy/backend/vm/spec/`：VM 稳定契约 — bytecode / opcode / ABI / state / effect protocol；**不得**依赖某个 Python VM instance。
  - `qy/backend/llvm/`：LLVM 验证后端；不取代 register VM。
  - `qy/backend/wasm/`：WebAssembly 验证后端（LIR → WAT，宿主 runtime 在 `qy/resources/wasm/runtime.js`）；不取代 register VM。
- `qy/vm/`：Register VM 的 Python 实现位置；实现 `qy/backend/vm/spec`，**不定义** VM target 规格。
- `qy/vm/instance/`：一次执行的可变运行实例（machine / frame / state）；**只能实现** `qy/backend/vm/spec`，不得定义 opcode / ABI 规格。
- `qy/runtime.py`：`Qy` / `AsyncQy` 主类 API，串联完整管线。
- `qy/std/`：标准 profile 与标准库的唯一实现位置（内置符号空间 `qy.core` / `qy.io` / `qy.num` / `qy.str` / `qy.char` / 数值空间等都在这里）；新增标准能力应进入这里。历史 `qy/symbol_space/` 与 `qy/stdlib/` 已删除。

### 工具与 CLI

- `qy/tools/check/`：analyzer / type checker。
- `qy/tools/fmt/`：formatter。
- `qy/tools/lsp/`：language server。
- `qy/benchmark/`：benchmark harness。
- `qy/cli/`：click CLI，包含 `run`、`repl`、`ast`、`expand`、`hir`、`mir`、`lir`、`bytecode`、`fmt`、`check`、`typecheck`、`operators`、`lsp`、`pkg`、`llvm`、`wasm`、`export`、`completion`。
- `tests/`：pytest 测试，基线 `uv run python -m pytest -q`。
- `examples/`：Qy 语言示例（`validation/`、`design/`、`host/`）。
- `extensions/qylang-support-vscode/`：VS Code 语言支持扩展。

## 常用命令

依赖和命令优先使用 `uv`：

```bash
uv run python -m pytest tests/ -v --cov=qy --cov-report=term-missing
uv run python -m pytest tests/test_register_vm.py -v

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
make bench
make bench-check
```

## 代码约定

- Python 目标版本是 3.12，包管理使用 `uv`。
- Ruff 配置在 `pyproject.toml`，行宽 100。
- 导入风格由 Ruff/isort 管理，当前配置偏好单行导入。
- 禁止包内相对导入，使用 `from qy.xxx import ...`。
- 目标包结构见 `docs/package-structure.md`。**不得**长期同时保留同名 `name.py` 与 `name/`；旧 `.py` 文件迁移时先把 public API 搬入目标 package `__init__.py`，再删除旧文件。`todo.md` §A0.2 与 `docs/package-structure.md` §5.1 列出已完成的迁移。
- 标准库目标是 `qy.std`；不得重新引入 `qy.symbol_space` / `qy.stdlib` 路径。
- 工程层包（`diag/source/session/build/project/import_/analysis/debug/errors`）只提供编译器基础设施，不得承载具体语言阶段语义。
- VM 必须区分 target spec 与 Python implementation：`qy/backend/vm/spec` 定义契约，`qy/vm` 实现该契约，`qy/vm/instance` 保存一次执行的可变状态；instance **不得**定义 opcode / ABI 规格。
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
- bytecode compiler 不允许重新理解 HIR/MIR 语义；语义 lowering 必须经由 LIR。
- Qy 不保留可选 runtime backend；不得新增或维护 IR VM / evaluator backend 语义。公共执行入口必须走 register VM。
- 公共 Python API 入口：`Qy`（`qy.runtime`）、`AsyncQy`（`qy.runtime`）、`compile_source_to_bytecode` / `compile_source_to_kind`（`qy.build.pipeline`）、`RegisterVirtualMachine`（`qy.vm.instance.machine`）。**已移除**的入口：`Qy.macroexpand_source`、`Qy.lower`、`Qy.lower_mir`、`Qy.compile_bytecode`、`Qy.evaluate_ir`、`Qy.evaluate_ir_source`、`qy.ir_vm.*`、`qy.evaluator`、`Qy(backend=...)`、`EvaluationBackend`。详见 `docs/pipeline.md` §"稳定 API 与删除对象"。
- 语言内核没有宿主环境；但标准实现总是围绕某个 `Qy` 实例展开，`pre-symbol-space-chain` 是该实例的初始查找链，reader、analyzer、LSP、lowering、runtime 都必须读取同一份实例事实。
- `pre-symbol-space-chain` 是链，不是单个特殊空间；standard profile、字面量空间、stdlib 空间、宿主注入空间都应以明确链节点建模。host reference/operator 必须通过实例链、显式注入或显式 import 进入 symbol-space-chain。
- runtime value 是 Qy 语义对象；Python value 只是当前实现或宿主互操作对象。两者不得混淆，跨宿主能力应通过 host reference / adapter 进入语言模型。
- chain 只负责 lookup；fold 才会把 binding 吸收到某个 symbol-space。`from` 是受 `exports` 约束的选择性 fold，module root 初始化也应使用同一模型。
- 语言核与默认 profile 分离；standard profile 可以预装 `+` 等常用算子，但这不把它们提升为核心 form。
- 新增 operator 前先判断能否由 Qy 自身实现；能写成 Qy library 的能力，不要下沉成 host operator。
- 用户自定义 operator 若需要被 analyzer / LSP 精确理解，创建者必须补充 arity、参数策略、参数/返回类型、effect 等声明；工具链不得凭实现细节猜测。
- `define` 只在当前 symbol-space 内一次性绑定，可以 shadow 链上后续 symbol-space 中的任意 symbol。
- 修改语言语义时，必须同步更新 `LANGUAGE.md` 与 `todo.md`。
- 修改 reader、lowering、IR 或 analyzer 时，同步考虑 CLI、LSP、formatter 和测试覆盖。

## 测试策略

- 窄改动优先运行相关测试文件。
- 涉及 MIR/LIR/bytecode/VM 时运行：`uv run python -m pytest tests/test_mir.py tests/test_lir.py tests/test_register_vm.py tests/test_register_vm_semantics.py tests/test_runtime.py -q`。
- 涉及 macro 时运行：`uv run python -m pytest tests/test_eval_macro.py tests/test_macroexpand.py tests/test_module_import.py -q`。
- 涉及 CLI 时运行 `tests/test_cli_commands.py` 与 `tests/test_qytest_runner.py`。
- 任何较大改动都要运行全量 `uv run python -m pytest -q` 和 `uv run ty check .`。

## 工作注意事项

- 当前仓库可能存在用户未提交改动；开始编辑前先看 `git status --short`，不要覆盖或回退非本次任务的修改。
- 文档或总结默认中文；代码标识符、公共 API、错误类型和命令保持英文原文。
- 不要把 `node_modules/`、`dist/`、`QyLang.egg-info/` 等生成物当作主要编辑目标。
- 如需新增操作符，新语义必须走 MIR / LIR / bytecode / VM；不得继续走 `PureOperator` / `ScopeOperator` / `ControlOperator` / `EffectOperator` / `MetaOperator` 这套 legacy operator dispatch。
- **CLI `qy FILE` 隐式重定向**：CLI 已从 typer 迁移到 click；`qy/cli/_app.py` 的 `QyGroup.resolve_command` fallback 在当前 click 下**正常工作**：`qy FILE` 等价 `qy run FILE`。推荐仍使用显式 `qy run FILE` 形式以避免与未来子命令名冲突。
- 每次完成工作后用一句话总结修改内容。