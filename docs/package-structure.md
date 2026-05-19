# Qy 包结构目标

本文档固定 Qy 的目标包结构。这里的“结构”不是单纯整理文件名，而是把每一层 pipeline 的所有权固定下来，避免语义在旧模块、兼容门面、CLI 和 VM 之间继续漂移。

当前优先级：**结构正确高于测试通过**。如果迁移期出现 import/test 失败，先记录失败来源；不要为了让测试暂时通过而继续扩散错误边界。

# 1. 目标树

```text
qy/
  diag/              # 统一诊断系统：diagnostic/reporter/fixit
  source/            # SourceFile/Span/SourceMap/位置映射
  session/           # 编译会话、配置、feature flags、profile facts
  build/             # 构建图、缓存、artifact、pipeline driver
  project/           # qy.toml、package/module、项目依赖
  import_/           # module loader/import resolver/from-fold bridge
  analysis/          # scope/ref/escape/liveness/effect analysis
  debug/             # IR dump、trace、VM debug、LLVM command log
  errors/            # 语言级异常与内部编译器错误分类
  frontend/          # source -> raw AST -> surface dialect
  macro/             # macro expand / hygiene / trace / compile-time namespace
  core/              # symbol / chain / binding / operator declaration / effect declaration
  sem/               # backend-facing value model and abstract machine semantics
  ir/
    hir/             # high-level semantic IR
    mir/             # CFG + virtual register IR
    lir/             # Qy abstract-machine IR
  passes/            # lowering / verification / rewrite passes
  backend/
    llvm/            # optional LLVM validation backend
    vm/              # VM target：spec + bytecode emit, not a second runtime backend
      spec/          # VM 规格：opcode/ABI/state/effect/bytecode contract
  vm/                # Python VM implementation：machine/frame/state/scheduler/host
    instance/        # VM 运行实例：machine/frame/state/scheduler/host adapter
  std/               # standard profile and standard library target package
  tools/
    check/           # analyzer / type checker
    fmt/             # formatter
    lint/            # source-level lint
    lsp/             # language server
  cli/
    commands/        # CLI command modules
  resources/         # runtime resources such as libqy
```

# 2. 所有权

- `diag`: 统一诊断模型、reporter、fixit；不承载语言级异常类。
- `source`: 统一源码文件、Span、SourceMap、位置映射；不承载 import/module 解析。
- `session`: 单次编译/执行会话的配置、feature flags、profile、source manager、diagnostic reporter；不得成为全局单例。
- `build`: build graph、artifact、cache、pipeline driver；只编排阶段，不实现阶段语义。
- `project`: `qy.toml`、package、module root、依赖、项目级 profile 配置；不执行 lowering/VM。
- `import_`: import resolver、module loader、from/fold 与 build graph 的连接层；不直接求值 module body。
- `analysis`: 作用域、引用、逃逸、活跃变量、effect analysis、类型/签名检查；不执行 runtime evaluation。
- `debug`: IR dump、trace、VM debug、LLVM command log；debug 输出不得修正语义。
- `errors`: 语言级异常、runtime error、compile error、internal compiler error 分类；Span 最终应来自 `source`。
- `frontend`: 只负责读取 source、构造 raw AST、执行 default surface dialect；不得提前创建 runtime value。
- `macro`: 负责 macro expansion、hygiene、source map、compile-time symbol-space；不得依赖 VM 执行路径。
- `core`: 保存语言核心模型，包括 symbol、immutable chain、binding slot、operator/effect 声明；不得混入 profile 便利算子。
- `sem`: 保存面向 libqy / VM / backend 的值模型和抽象机语义；不得反向依赖 parser、CLI 或 std。
- `ir/hir`: 只表达 resolved binding、structured control、operator/effect/module facts。
- `ir/mir`: 只表达 CFG、virtual register、显式 control/effect flow。
- `ir/lir`: 表达 Qy abstract machine：layout、ABI、virtual stack、continuation frame、handler frame、symbol-space-chain transition、lookup operation、slot operation、fixup、peephole、debug injection。
- `passes`: 只放阶段变换；IR model 不得 import `passes`。
- `backend`: 非核心验证/输出后端；不得引入第二 runtime backend。
- `backend/vm`: VM target 的规格、bytecode emit、验证与适配；不是 Python VM 实现。
- `backend/vm/spec`: 稳定 VM 规格，包括 bytecode、opcode、operand schema、ABI、abstract state、effect/continuation protocol；不得依赖某个 Python VM instance。
- `vm`: Qy Register VM 的 Python 实现位置；实现 `backend/vm/spec`，不定义 VM target 规格。
- `vm/instance`: 一次执行的可变运行实例，包括 machine、runtime frame、runtime state、scheduler、host adapter；只能实现 `backend/vm/spec`，不得定义 opcode/ABI 规格。
- `std`: standard profile 与标准库目标包；`qy/stdlib` 只是迁移期兼容目录。
- `tools`: 面向维护者和编辑器的工具；读取同一 Qy 实例事实，不私造语言规则。
- `cli`: 只编排 public API 和工具入口，不承载语言语义。

# 3. 导入方向

- `diag -> source`，不得依赖 pipeline stage。
- `errors -> source`，不得依赖 `diag` reporter 或 VM。
- `session -> source/diag/project`，不得依赖 concrete CLI。
- `project -> source/session`，不得依赖 VM。
- `import_ -> project/build/source`，不得依赖 register VM。
- `analysis -> hir/mir/core/session/diag`，不得执行 runtime evaluation。
- `frontend -> source/core/diag/errors`。
- `macro -> frontend/core/source/diag/compile-time`，不得 import `register_vm` 作为长期方案。
- `ir.* -> source/diag/errors/reader type`；不得 import `passes`、`vm`、`std`。
- `passes -> ir/core/sem/session/diag`；不得把语义补丁写进 CLI 或 VM。
- `backend/vm/spec -> lir/core/sem/errors`；不得依赖 `qy/vm`。
- `backend/vm/emit -> backend/vm/spec/lir/diag`；不得重新解释 HIR/MIR 语义。
- `vm/instance -> backend/vm/spec/core/sem/runtime values/errors/debug`；不得依赖 legacy evaluator。
- `std -> public runtime adapters`；不得直接依赖 `qy.evaluator`。
- `tools/cli -> public API`；不得定义私有语言语义。

# 4. 同名模块冲突

同一目录下不得长期同时存在 `name.py` 与 `name/`。Python import 会优先解析其中一个，导致另一个实现被静默遮蔽。

当前必须收口的冲突：

- `qy/macro.py` -> `qy/macro/__init__.py`，旧文件删除。
- `qy/cli.py` -> `qy/cli/__init__.py` + `qy/cli/commands/*`，旧文件删除。
- `qy/ir.py` -> `qy/ir/__init__.py`，旧文件删除。
- `qy/mir.py` -> `qy/ir/mir/__init__.py`，旧文件删除。
- `qy/lir.py` -> `qy/ir/lir/__init__.py`，旧文件删除。
- `qy/errors.py` -> `qy/errors/__init__.py`，旧文件删除。
- `qy/ir/hir.py` -> `qy/ir/hir/__init__.py` 或 `qy/ir/hir/node.py`，旧文件删除。
- `qy/ir/mir.py` -> `qy/ir/mir/__init__.py` 或 `qy/ir/mir/node.py`，旧文件删除。
- `qy/ir/lir.py` -> `qy/ir/lir/__init__.py` 或 `qy/ir/lir/node.py`，旧文件删除。

迁移规则：

- 第一阶段可以把旧 `.py` 的 public 内容搬进目标 package `__init__.py`，确保 import 语义先稳定。
- 第二阶段再把 `__init__.py` 中的实现拆到 `node.py`、`build.py`、`verify.py`、`pretty.py` 等内部模块。
- 旧 `.py` 文件一旦被目标 package 覆盖，不再作为兼容 shim；应在同一批迁移中删除或标记为待删。

# 5. Legacy 文件迁移表

- `qy/lowering.py` -> `qy/passes/lower_hir.py`。
- `qy/mir_lowering.py` -> `qy/passes/lower_mir.py`。
- `qy/lir_lowering.py` -> `qy/passes/lower_lir.py`。
- `qy/ir.py` -> `qy/ir/__init__.py`。
- `qy/mir.py` -> `qy/ir/mir/__init__.py`。
- `qy/lir.py` -> `qy/ir/lir/__init__.py`。
- `qy/errors.py` -> `qy/errors/__init__.py`，再拆分为 `language.py`、`compiler.py`、`internal.py` 等。
- `qy/diagnostics.py` -> `qy/diag/diagnostic.py`。
- `qy/reader.SourceSpan` / `qy.errors.SourceSpan` -> `qy/source/span.py`。
- `qy/source_modules.py` -> `qy/import_/loader.py` 与 `qy/project/module.py`。
- `qy/bytecode.py` -> `qy/backend/vm/spec/bytecode.py`。
- `qy/bytecode_compiler.py` -> `qy/vm/emit.py`。
- `qy/register_vm.py` -> `qy/vm/instance/machine.py`。
- `qy/virtual_stack.py` -> `qy/vm/instance/frame.py` / `state.py`。
- `qy/analyzer.py` -> `qy/tools/check/`。
- `qy/formatter.py` -> `qy/tools/fmt/`。
- `qy/lsp.py` -> `qy/tools/lsp/`。
- `qy/benchmark.py` -> `qy/tools/bench.py` 或 `bench/`。
- `qy/stdlib/*` -> `qy/std/*`。

# 5.1 删除计划

删除按三类推进，不允许无限期保留兼容文件。

## 可直接删除

这些不是源码真源，确认没有被构建脚本需要后可直接删除：

- `qy/**/__pycache__/`
- `.pytest_cache/`
- `.ruff_cache/`
- `.mypy_cache/` / `.ty/` 一类本地检查缓存
- `QyLang.egg-info/`
- `dist/`
- packaging 临时 `build/`
- `*.py.original`
- `*.py.restored`

## 迁移后删除

这些文件仍可能被 public API 引用，必须先完成目标包迁移与 import 更新：

- `qy/macro.py` -> `qy/macro/__init__.py` 后删除。
- `qy/cli.py` -> `qy/cli/__init__.py` + `qy/cli/commands/*` 后删除。
- `qy/errors.py` -> `qy/errors/__init__.py` 后删除。
- `qy/diagnostics.py` -> `qy/diag/diagnostic.py` 后删除。
- `qy/reader.py` -> `qy/frontend/` + `qy/source/` 边界稳定后删除或改为短期 public shim。
- `qy/ir.py` -> `qy/ir/__init__.py` 后删除。
- `qy/mir.py` -> `qy/ir/mir/__init__.py` 后删除。
- `qy/lir.py` -> `qy/ir/lir/__init__.py` 后删除。
- `qy/ir/hir.py` -> `qy/ir/hir/__init__.py` / `node.py` 后删除。
- `qy/ir/mir.py` -> `qy/ir/mir/__init__.py` / `node.py` 后删除。
- `qy/ir/lir.py` -> `qy/ir/lir/__init__.py` / `node.py` 后删除。
- `qy/lowering.py` -> `qy/passes/lower_hir.py` 后删除。
- `qy/mir_lowering.py` -> `qy/passes/lower_mir.py` 后删除。
- `qy/lir_lowering.py` -> `qy/passes/lower_lir.py` 后删除。
- `qy/bytecode.py` -> `qy/backend/vm/spec/bytecode.py` 后删除。
- `qy/bytecode_compiler.py` -> `qy/vm/emit.py` 后删除。
- `qy/register_vm.py` -> `qy/vm/instance/machine.py` 后删除。
- `qy/virtual_stack.py` -> `qy/vm/instance/frame.py` / `state.py` 后删除。
- `qy/analyzer.py` -> `qy/analysis/` + `qy/tools/check/` 后删除。
- `qy/formatter.py` -> `qy/tools/fmt/` 后删除。
- `qy/lsp.py` -> `qy/tools/lsp/` 后删除。
- `qy/benchmark.py` -> `qy/tools/bench.py` 或 `bench/` 后删除。
- `qy/source_modules.py` -> `qy/import_/loader.py` + `qy/project/module.py` 后删除。
- `qy/llvm_codegen.py` -> `qy/backend/llvm/` 后删除。
- `qy/types.py` -> `qy/core/` 或 `qy/sem/` 后删除；这是修复 console-script 启动时遮蔽 stdlib `types` 的结构前提。

## 语义替代后删除

这些是 legacy 语义承载点，不能只靠搬文件删除，必须先完成新语义：

- `qy/evaluator.py`：register VM 与 macro compile-time 执行完全接管后删除。
- `qy/eval_runtime.py`、`qy/async_runtime.py`、`qy/symbol_utils.py`：`std` 不再通过 legacy evaluator helper 后删除。
- `qy/operators.py`、`qy/operator_runtime.py`、`qy/operator_signature.py`、`qy/operator_docs.py`：operator metadata/schema 进入 core/std/profile 统一模型后删除或拆迁。
- `qy/runtime_values.py`、`qy/environment.py`、`qy/continuation.py`：runtime value、symbol-space、continuation frame 进入 core/sem/vm spec/instance 后删除或拆迁。
- `qy/values.py`、`qy/literals.py`、`qy/semantics.py`：syntax/runtime value 分层完成后迁入 `core/` 或 `sem/`，旧文件删除。
- `qy/stdlib/`：迁入 `qy/std/` 且 compat import 期结束后删除。

# 5.2 VM target spec / Python VM implementation 分层

```text
backend/vm/
  spec/
    bytecode.py      # bytecode program/function/instruction spec
    opcode.py        # opcode set, operand schema, register/branch effects
    abi.py           # call ABI, frame ABI, handler/continuation ABI
    state.py         # abstract VM state contract
    effect.py        # perform/handle/resume low-level protocol
  emit.py            # verified LIR -> VM bytecode

vm/
  instance/
    machine.py       # RegisterVirtualMachine instance and dispatch loop
    frame.py         # runtime frame objects
    state.py         # mutable execution state
    scheduler.py     # parallel/all/race runtime scheduling
    host.py          # host adapter / host callable bridge
  emit.py            # Python VM local compatibility only; not final bytecode emit
  debug.py           # VM-specific debug hooks
```

边界规则：

- `backend/vm/spec` 是 VM target 契约，`qy/vm` 是该 target 的 Python 实现。
- spec 可以被 LIR lowering、bytecode verifier、Python VM implementation、LLVM/libqy validation 共用。
- `qy/vm/instance` 只能实现 spec，不能定义或修改 opcode、ABI、operand schema。
- `backend/vm/emit` 写入 spec 规定的数据结构，不得把 HIR/MIR 语义补到 emit 阶段。
- debug 只能观察 spec/instance，不得参与语义修正。

# 5.3 工程层子包建议

这些包属于 compiler infrastructure，不属于语言语义本体：

```text
source/
  file.py
  span.py
  sourcemap.py

diag/
  diagnostic.py
  reporter.py
  fixit.py

session/
  config.py
  context.py
  options.py

build/
  pipeline.py
  artifact.py
  cache.py
  graph.py
  driver.py

project/
  manifest.py
  package.py
  module.py

import_/
  resolver.py
  loader.py

analysis/
  scope.py
  refs.py
  escape.py
  liveness.py
  effects.py

debug/
  dump.py
  trace.py
  vm.py
  llvm.py
```

`import_` 使用尾随下划线是为了避免和 Python 关键字 `import` 冲突。

# 6. 占位文件格式

新增占位文件必须使用中文 docstring，最少说明三件事：

- 目标：该包最终负责什么。
- 当前：当前是否只是占位、是否仍依赖 legacy 文件。
- 禁止：这里不能承担什么职责。

推荐格式：

```python
"""模块职责。

目标：
- ...

当前：
- ...

禁止：
- ...
"""
```

# 7. 当前推进顺序

1. 固定本文档、`AGENTS.md`、`CLAUDE.md`、`todo.md` 中的目标结构。
2. 建立 compiler infrastructure 包：`diag/source/session/build/project/import_/analysis/debug/errors`。
3. 建立 VM 分层：`qy/backend/vm/spec/` 与 `qy/vm/instance/`。
4. 建立 `qy/std/` 目标包，停止新增 `qy/stdlib/` 文件。
5. 修复 `passes` 命名错位：`lower_mir.py` 必须是 HIR -> MIR，`lower_lir.py` 必须是 MIR -> LIR。
6. 解决同名 `macro`、`cli`、`errors` 冲突。
7. 解决 `ir/hir`、`ir/mir`、`ir/lir` 冲突。
8. 迁移 source/diag/session/project/import/build 的 legacy 文件。
9. 按 VM target spec / Python VM implementation 分层迁移 VM 文件，再删除 top-level 旧文件。
10. 迁移 CLI 到 `qy/cli/commands/`，再删除 `qy/cli.py`。
11. 迁移 stdlib 到 `qy/std/`，保留短期 `qy/stdlib` 兼容入口，最后删除。
