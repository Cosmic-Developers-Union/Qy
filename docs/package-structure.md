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
  vm/                # bytecode / register VM / stack / debug / VM emit
  backend/
    llvm/            # optional LLVM validation backend
    vm/              # VM backend adapters, not a second runtime backend
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
- `vm`: register VM 的唯一实现位置；bytecode compiler 只消费 LIR，不重新理解 HIR/MIR 语义。
- `backend`: 非核心验证/输出后端；不得引入第二 runtime backend。
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
- `vm -> bytecode/lir/core/sem/runtime values/errors/debug`；不得依赖 legacy evaluator。
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
- `qy/bytecode.py` -> `qy/vm/bytecode.py`。
- `qy/bytecode_compiler.py` -> `qy/vm/emit.py`。
- `qy/register_vm.py` -> `qy/vm/interp.py`。
- `qy/virtual_stack.py` -> `qy/vm/stack.py`。
- `qy/analyzer.py` -> `qy/tools/check/`。
- `qy/formatter.py` -> `qy/tools/fmt/`。
- `qy/lsp.py` -> `qy/tools/lsp/`。
- `qy/benchmark.py` -> `qy/tools/bench.py` 或 `bench/`。
- `qy/stdlib/*` -> `qy/std/*`。

# 5.1 工程层子包建议

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
3. 建立 `qy/std/` 目标包，停止新增 `qy/stdlib/` 文件。
4. 修复 `passes` 命名错位：`lower_mir.py` 必须是 HIR -> MIR，`lower_lir.py` 必须是 MIR -> LIR。
5. 解决同名 `macro`、`cli`、`errors` 冲突。
6. 解决 `ir/hir`、`ir/mir`、`ir/lir` 冲突。
7. 迁移 source/diag/session/project/import/build 的 legacy 文件。
8. 迁移 VM 文件到 `qy/vm/`，再删除 top-level 旧文件。
9. 迁移 CLI 到 `qy/cli/commands/`，再删除 `qy/cli.py`。
10. 迁移 stdlib 到 `qy/std/`，保留短期 `qy/stdlib` 兼容入口，最后删除。
