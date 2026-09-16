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
  passes/            # staged transforms and analyses, organized by phase + topic
    pipeline.py      # pass scheduler and dump/stop support
    pass_base.py     # Pass / PassContext / PassResult
    raw/
    surface/
    macro/
    core/
    resolve/
    hir/
    closure/
    effect/
    control/
    mir/
    lir/
    optimize/
    emit/
  backend/
    llvm/            # optional LLVM validation backend
    wasm/            # WebAssembly backend: LIR -> WAT + abi（宿主 runtime 在 qy/resources/wasm/）
    vm/              # VM target：spec + bytecode emit, not a second runtime backend
      spec/          # VM 规格：opcode/ABI/state/effect/bytecode contract
  vm/                # Python VM implementation：machine/frame/state/scheduler/host
    instance/        # VM 运行实例：machine/frame/state/scheduler/host adapter
  ext/               # 标准扩展机制：宿主能力唯一入口（descriptor/registry + 内置扩展）
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
- `analysis`: 活跃变量分析（liveness）；作用域/引用/逃逸/类型检查已收敛到 canonical frontend + HIR verifier，不执行 runtime evaluation。
- `debug`: IR dump、trace、VM debug、LLVM command log；debug 输出不得修正语义。
- `errors`: 语言级异常、runtime error、compile error、internal compiler error 分类；Span 最终应来自 `source`。
- `frontend`: 只负责读取 source、构造 raw AST、执行 default surface dialect；不得提前创建 runtime value。
- `macro`: 负责 macro expansion、hygiene、source map、compile-time symbol-space；不得依赖 VM 执行路径。
- `core`: 保存语言核心模型，包括 symbol、immutable chain、binding slot、operator/effect 声明；不得混入 profile 便利算子。
- `sem`: 保存面向 libqy / VM / backend 的值模型和抽象机语义；不得反向依赖 parser、CLI 或 std。
- `ir/hir`: 只表达 resolved binding、structured control、operator/effect/module facts。
- `ir/mir`: 只表达 CFG、virtual register、显式 control/effect flow。
- `ir/lir`: 表达 Qy abstract machine：layout、ABI、virtual stack、continuation frame、handler frame、symbol-space-chain transition、lookup operation、slot operation、fixup、peephole、debug injection。
- `passes`: 只放变换和分析，按“阶段 + 主题”组织；IR model 不得 import `passes`。
- `backend`: 非核心验证/输出后端；不得引入第二 runtime backend。
- `backend/llvm`: LLVM IR 输出后端（验证用），宿主 runtime 在 `qy/resources/libqy/`。
- `backend/wasm`: WebAssembly text（WAT）输出后端（验证用），宿主 runtime 在 `qy/resources/wasm/runtime.js`；只消费 compat LIR，不定义 opcode 规格。
- `backend/vm`: VM target 的规格、bytecode emit、验证与适配；不是 Python VM 实现。
- `backend/vm/spec`: 稳定 VM 规格，包括 bytecode、opcode、operand schema、ABI、abstract state、effect/continuation protocol；不得依赖某个 Python VM instance。
- `vm`: Qy Register VM 的 Python 实现位置；实现 `backend/vm/spec`，不定义 VM target 规格。
- `vm/instance`: 一次执行的可变运行实例，包括 machine、runtime frame、runtime state；只能实现 `backend/vm/spec`，不得定义 opcode/ABI 规格。
- `ext`: Qy 与宿主环境之间**唯一**的官方边界。扩展用 `ExtensionDescriptor` 声明名字 / 可导入模块名 / 所需 capability / binding signature；宿主实现只出现在 `qy/ext/*`。语言内核（`core/frontend/ir/analysis/backend/vm/spec`）不得 import `qy.ext.*`；`qy.io` 等标准模块也不得内嵌宿主机能（文件系统、进程、Python 执行）。
- `std`: standard profile 与标准库目标包；内置符号空间实现全部位于此包，`symbol_space/` 与 `qy/stdlib` 兼容目录已删除。
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
- `backend/wasm -> lir/backend/wasm/abi`；不得重新解释 HIR/MIR 语义，也不得被内核反向依赖。
- `backend/vm/emit -> backend/vm/spec/lir/diag`；不得重新解释 HIR/MIR 语义。
- `vm/instance -> backend/vm/spec/core/sem/runtime values/errors/debug`。
- `ext -> core/sem/import_`；实现宿主能力，但不得被内核反向依赖。
- `std -> ext` 仅允许 re-export 已声明扩展 binding，不得自行实现宿主机能。
- `std -> public runtime adapters`。
- `tools/cli -> public API`；不得定义私有语言语义。

# 3.1 Pass 组织与顺序

核心原则：

```text
ir/       只放数据结构
passes/   只放变换和分析
backend/  只放目标后端输出
```

目标目录：

```text
passes/
  pipeline.py
  pass_base.py
  build.py
  frontend/cst_parse.py          # 已实现
  frontend/reader_macro.py       # 已实现
  frontend/surface_normalize.py  # 已实现（surface 规约的唯一实现）
  raw/validate.py                # 已实现（raw AST 只能是 symbol/chain/nil）
  macro/expand.py                # 已实现（hygiene 由 qy/macro/hygiene.py 实现，无独立 pass）
  resolve/spaces.py              # 已实现（HIR symbol-space layout：id/parent/slot）
  hir/lower.py                   # 已实现（symbol 解析 / import 解析都在这里）
  hir/lower_pass.py              # 已实现
  hir/validate.py                # 已实现（H1-H14）
  closure/convert.py             # 未实现（唯一保留的 closure 迁移目标）
  effect/analyze.py              # 已实现（effect 事实 + EA1 escaping hint）
  control/tailcall.py            # 已实现，仅 build_optimization_pipeline 子管线
  control/cfg_simplify.py        # 已实现，仅 build_optimization_pipeline 子管线
  mir/lower_pass.py              # 已实现
  mir/normalize.py               # 已实现
  mir/validate.py                # 已实现
  lir/lower.py                   # 已实现
  lir/lower_pass.py              # 已实现
  lir/linearize.py               # 已实现
  lir/compact.py                 # 已实现
  lir/peephole.py                # 已实现
  lir/effects.py                 # 已实现并接线（abstract-machine dialect，PipelineOptions.lir_dialect）
  lir/spaces.py                  # 已实现（消费 program-level layout：SS_ENTER/SS_LEAVE/SLOT_COMPLETE，不重建 layout）
  lir/verify.py                  # 已实现
  optimize/*.py                  # 已实现，仅 build_optimization_pipeline 子管线
  emit/bytecode.py               # 已实现（LLVM 输出在 qy/backend/llvm/）
```

已删除的重复占位（职责已被现有实现覆盖，不再保留空文件）：
`macro/hygiene.py`（→ `qy/macro/hygiene.py`）、`core/desugar.py`（→
`qy/frontend/surface.py` + `qy/core/quasiquote.py`）、`core/validate.py`（→
`hir.lower` + H1–H14）、`resolve/symbols.py` / `resolve/imports.py`（→ `hir.lower` +
`qy/import_`）、`control/loop.py`（→ `control/loop_opt.py`）、`lir/normalize.py`
（→ `lir/linearize` + `lir/peephole` + `lir/compact`）、`emit/llvm_prepare.py`
（→ `qy/backend/llvm/`）、`effect/lower.py` / `effect/flatten.py`（effect lowering
是 LIR 职责，见 `docs/ir-design.md`），以及空的 `passes/surface/` 目录。

当前实际管线 pass 顺序（`build_default_pipeline()`，`qy/build/pipeline.py`）：

```text
frontend.cst_parse
-> frontend.reader_macro
-> raw.validate
-> frontend.surface_normalize
-> macro.expand
-> hir.lower
-> resolve.spaces
-> hir.validate
-> effect.analyze
-> mir.lower
-> mir.validate
-> lir.lower（内部: linearize -> lower_compat_effects -> peephole -> compact_registers）
-> lir.verify
-> emit.bytecode
```

默认管线包含 `optimize.mir` 接线点，但 `PipelineOptions.optimize` 默认为 **False**，
因此默认不运行 MIR 优化 pass。`qy/passes/optimize/*` 与 `control/cfg_simplify` /
`control/tailcall` / `control/loop_opt` 已实现并有隔离测试，顺序真源是
`qy/passes/optimize/apply.py::OPTIMIZE_PASSES`。

**实测证据**：用 `uv run python scripts/optimize_frontier.py`（每个 `.qy` 独立子进程，
结果做规范化后对比；早期进程内测量因 repr 含内存地址与 pass name 重复而失真，数值不可用）
在 86 个语料（`examples/validation|design`、`tests/qy`、`meta-interp/cases`）上测得：

| 优化子集 | 结果不一致 |
| --- | --- |
| S1 仅简化（const_prop/const_fold/copy_prop/dce/dse） | **0/86** |
| S2 + cse / strength_reduce | **0/86** |
| S3 + cfg_simplify / tailcall / licm / loop_opt | **0/86** |
| S4 + inline / aggressive_inline / scalar_replace / intern | **0/86** |
| S5 + reg_alloc | **0/86** |

即：**86 个语料在全部优化子集下与未优化结果一致**（`optimize=True` 目前仍非默认，
见下方开关说明）。

已修复的真实缺陷（S1 11/86 → 0，S3 11/86 → 0，S5 42/86 → 11）：

- `const_prop` 曾把 CALL 的**参数寄存器号替换成常量池下标**（两者都是 `int`，verifier
  无法分辨），运行时会读错寄存器；同时它把程序里被 `define`/`let`/`from` shadow 的
  名字也当字面量，且文档承诺的 `LOAD_ENV` 字面量降级从未实现。现已改为：仅当拼写
  在程序内未被 shadow 时才把 `LOAD_ENV` 降成 `LOAD_CONST`；
- `const_fold` 会在算子名被 shadow 时（如 `(let ((+ (lambda (a b) 0))) (+ 41 1))`）
  折叠成内置算子，且用"跨块最后一次写寄存器"当定义（不支配使用点）。现已加入
  shadow 守卫与「寄存器在函数内唯一被定义」要求；
- 多个 optimize/control pass 重建 `MIRProgram`/`LIRProgram` 时丢弃了
  `symbol_spaces`，现在统一走 `passes/optimize/facts.rebuild_program`。

随后又修复了控制流与寄存器分配阶段的四类缺陷：

- `cfg_simplify` / `licm` / `loop_opt` / `analysis.liveness` 各自维护了一份 CFG
  后继实现，都只认 `JUMP`/`BRANCH`，把 `EFFECT_PERFORM` 的 **resume 块**当作不可达
  删除或漏算活跃区间。现在统一走 `qy.ir.mir.terminator_targets` 与
  `terminator_target_positions`（含 effect resume 边与重映射）；
- `liveness` 完全没有收集 terminator 的寄存器使用（`live_out` 只并后继块的
  live_in），导致只在 `TAIL_CALL`/`RETURN`/`BRANCH` 中被读取的寄存器活跃区间提前
  结束，`reg_alloc` 把它们复用成同一物理寄存器；
- `reg_alloc` 手写 per-opcode 重映射，漏掉 `EFFECT_HANDLE_END` / `DEFINE_MODULE` /
  `CACHE_EVAL` 等的寄存器操作数；现在 `qy.ir.mir` 提供
  `register_operand_positions` / `register_def_position` / `terminator_*` 唯一表，
  liveness 与 reg_alloc 共用；`0..len(params)-1` 仍按 LIR `compact_registers` 的
  参数槽约定保留；
- `intern` 用 `hash(value)` 当去重键（`T` 与 `none` 都是空 frozen dataclass，hash
  相同），且合并了 identity 可观察的 symbol/字符串常量（当前 `=`
  对它们按 identity 比较，`(= "abc" "abc")` 为 `nil`）。现在只对数值与自身对象
  单例去重。

随后又修复了 effect 重编号与内联健全性：

- `qy.ir.mir.register_operand_positions` 漏了 `EFFECT_RESUME` 的 value 寄存器
  （`EFFECT_RESUME(dst, cont, value)` 只返回前两个位置），`reg_alloc` 重编号后 resume
  会传回旧寄存器里的陈旧值：`(handle (perform ping 42) ((ping (v k) (resume k (+ v 8)))))`
  在 optimize=True 下得到 8 而非 50。现在位置为 (0,1,2)，且 `register_def_position`
  返回 0（resume 结果寄存器）；
- `optimize.inline` 与 `optimize.aggressive_inline` 各自复制了一份内联实现，都缺少
  闭包健全性：把引用闭包变量的 lambda 内联进调用者，导致 `unresolved symbol 'f'`；
  形参在 MIR 里按名字读取，内联时又没有替换成实参寄存器；`_offset_instruction` 的兜底
  分支还会给**所有** int 操作数加偏移（常量池下标 / 函数下标 / space id 都会被改坏）；
  effect 守卫写的是 `HANDLE`/`PERFORM` 等从未存在的 opcode，属于死代码。
  现在两份实现收口到 `qy/passes/optimize/inline_core.py`（“唯一事实源”）：健全性判定
  （闭包变量 / 空间副作用 / 嵌套 lambda / effect）、形参替换、寄存器位移（走
  `qy.ir.mir` 寄存器表）都在内核里，两个 pass 只保留策略（单调用点 vs 多调用点 +
  指令预算 + 深度）。

在把 `optimize=True` 设为默认之前仍需：全量测试在 optimize 下跑通、确认对
bytecode 体积/性能有实际收益，并按 `todo.md` 记录开启条件。

目标 pass 顺序（完整管线）：

```text
frontend.cst_parse             # 已实现
-> frontend.reader_macro       # 已实现
-> raw.validate                # 已实现
-> frontend.surface_normalize  # 已实现
-> macro.expand                # 已实现
-> resolve.spaces              # 已实现
-> hir.lower                   # 已实现
-> hir.validate                # 已实现
-> effect.analyze              # 已实现
-> closure.convert             # 未实现
-> control.tailcall            # 已实现，仅优化子管线
-> control.cfg_simplify        # 已实现，仅优化子管线
-> mir.normalize               # 内部工具模块，由 mir.lower 调用
-> mir.validate                # 已实现
-> lir.lower                   # 已实现
-> lir.verify                  # 已实现
-> optimize.const_fold / optimize.dce / optimize.inline   # 仅优化子管线
-> emit.bytecode               # 已实现
-> backend（LLVM / WASM / VM）
```

最重要的 pass：

- `resolve.spaces`: 符号提升、space layout、binding slot、pending binding、meta-space。
- `effect.analyze`: one-shot/multi-shot、continuation escape、parallel effect 边界。
- `effect.flatten`: continuation / handler / resume -> CFG/state。
- `closure.convert`: lambda -> closure/env，捕获和 slot copy policy 显式化。
- `lir.verify`: LIR frame、handler、continuation、slot、lookup、branch 可验证性。

`passes/pipeline.py` 必须支持调试截断与 dump：

```bash
qy emit main.qy --after=effect.flatten
qy emit main.qy --target=lir
```

`--after=<pass-id>` 表示运行到该 pass 后 dump artifact；`--target=<artifact>` 表示运行到目标产物后停止。

**当前状态**：`raw.validate`、`resolve.spaces`、`effect.analyze` 已实现并接入默认管线；
`closure.convert` 是唯一保留的未实现 pass（closure/env 捕获目前由 `hir.lower` 的
symbol-space 链隐式承担）。effect lowering 不是独立 pass：它是 LIR 职责
（`lir/lower.py` + `passes/lir/effects.py` / `compat_effects.py`），因为
`handle`/`perform`/`resume` 到 LIR 边界后不应再作为语言级指令存在。

# 4. 同名模块冲突（已全部解决）

同一目录下不得长期同时存在 `name.py` 与 `name/`。Python import 会优先解析其中一个，导致另一个实现被静默遮蔽。

已解决的冲突（全部 ✅）：

- ~~`qy/macro.py`~~ → `qy/macro/__init__.py` ✅
- ~~`qy/cli.py`~~ → `qy/cli/__init__.py` + `qy/cli/commands/*` ✅
- ~~`qy/ir.py`~~ → `qy/ir/__init__.py` ✅
- ~~`qy/mir.py`~~ → `qy/ir/mir/__init__.py` ✅
- ~~`qy/lir.py`~~ → `qy/ir/lir/__init__.py` ✅
- ~~`qy/errors.py`~~ → `qy/errors/__init__.py` ✅
- ~~`qy/ir/hir.py`~~ → `qy/ir/hir/__init__.py` / `node.py` ✅
- ~~`qy/ir/mir.py`~~ → `qy/ir/mir/__init__.py` / `node.py` ✅
- ~~`qy/ir/lir.py`~~ → `qy/ir/lir/__init__.py` / `node.py` ✅

迁移规则（仍适用）：

- 第一阶段可以把旧 `.py` 的 public 内容搬进目标 package `__init__.py`，确保 import 语义先稳定。
- 第二阶段再把 `__init__.py` 中的实现拆到 `node.py`、`build.py`、`verify.py`、`pretty.py` 等内部模块。
- 旧 `.py` 文件一旦被目标 package 覆盖，不再作为兼容 shim；应在同一批迁移中删除或标记为待删。

# 5. Legacy 文件迁移表

- `qy/lowering.py` -> `qy/passes/lower_hir.py`。
- `qy/mir_lowering.py` -> `qy/passes/closure` + `effect` + `control` + `mir`。
- `qy/lir_lowering.py` -> `qy/passes/lir/lower.py`。
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
- `qy/stdlib/*` -> `qy/std/*`（已完成，兼容 shim 已删除）。

# 5.1 删除计划

删除按三类推进，不允许无限期保留兼容文件。

标记规则：

- 迁移后删除文件使用 `QY_DELETE_AFTER_MIGRATION: target=...`。
- 语义替代后删除文件使用 `QY_DELETE_AFTER_SEMANTIC_REPLACEMENT: target=...`。
- 后续用 `rg QY_DELETE_AFTER qy` 审计待删范围。

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

## 迁移后删除（已完成）

以下文件已全部完成迁移并删除，禁止回归：

- ~~`qy/macro.py`~~ → `qy/macro/__init__.py` ✅
- ~~`qy/cli.py`~~ → `qy/cli/__init__.py` + `qy/cli/commands/*` ✅
- ~~`qy/errors.py`~~ → `qy/errors/__init__.py` ✅
- ~~`qy/diagnostics.py`~~ → `qy/diag/diagnostic.py` ✅
- ~~`qy/reader.py`~~ → `qy/frontend/` + `qy/source/` ✅
- ~~`qy/ir.py`~~ → `qy/ir/__init__.py` ✅
- ~~`qy/mir.py`~~ → `qy/ir/mir/__init__.py` ✅
- ~~`qy/lir.py`~~ → `qy/ir/lir/__init__.py` ✅
- ~~`qy/ir/hir.py`~~ → `qy/ir/hir/__init__.py` / `node.py` ✅
- ~~`qy/ir/mir.py`~~ → `qy/ir/mir/__init__.py` / `node.py` ✅
- ~~`qy/ir/lir.py`~~ → `qy/ir/lir/__init__.py` / `node.py` ✅
- ~~`qy/lowering.py`~~ → `qy/passes/hir/lower.py` ✅
- ~~`qy/mir_lowering.py`~~ → `qy/passes/mir/normalize.py` ✅
- ~~`qy/lir_lowering.py`~~ → `qy/passes/lir/lower.py` ✅
- ~~`qy/passes/lower_hir.py`~~ → staged passes ✅
- ~~`qy/passes/lower_mir.py`~~ → `mir/normalize.py` ✅
- ~~`qy/passes/lower_lir.py`~~ → `lir/lower.py` ✅
- ~~`qy/bytecode.py`~~ → `qy/backend/vm/bytecode.py` ✅
- ~~`qy/bytecode_compiler.py`~~ → `qy/backend/vm/compiler.py` ✅
- ~~`qy/register_vm.py`~~ → `qy/vm/instance/machine.py` ✅
- ~~`qy/virtual_stack.py`~~ → `qy/vm/instance/frame.py` / `state.py` ✅
- ~~`qy/analyzer.py`~~ → `qy/analysis/` + `qy/tools/check/` ✅
- ~~`qy/formatter.py`~~ → `qy/tools/fmt/` ✅
- ~~`qy/lsp.py`~~ → `qy/tools/lsp/` ✅
- ~~`qy/source_modules.py`~~ → `qy/import_/loader.py` + `qy/project/module.py` ✅
- ~~`qy/llvm_codegen.py`~~ → `qy/backend/llvm/` ✅
- ~~`qy/types.py`~~ → `qy/core/` 或 `qy/sem/` ✅

## 语义替代后删除（部分已完成）

- ~~`qy/evaluator.py`~~：已删除。register VM 与 macro compile-time 执行已完全接管 ✅。
- ~~`qy/eval_runtime.py`~~：已删除 ✅。
- ~~`qy/async_runtime.py`~~：已删除 ✅。
- ~~`qy/runtime_values.py`~~：已删除 ✅。
- ~~`qy/environment.py`~~：已删除。`Environment` 现为 `RuntimeSpace` 的类型别名 ✅。
- ~~`qy/operator_docs.py`~~：已删除 ✅。
- `qy/std/`：standard profile 与内置符号空间的唯一实现位置；`qy/symbol_space/` 与 `qy/stdlib/` 均已删除。
- ~~`qy/python_codegen.py`~~：已删除 ✅。
- `qy/operators.py`、`qy/operator_runtime.py`、`qy/operator_signature.py`：operator metadata/schema 进入 core/std/profile 统一模型后删除或拆迁。**当前状态**：`qy/core/operators.py` 已承载 operator 类型层级，`qy/core/operator_signature.py` 已承载签名模型；legacy 迁移完成。
- `qy/symbol_utils.py`：当前仍在 `qy/core/symbol_utils.py`，承载符号工具函数。**当前状态**：已迁移至 core，不再是 legacy 文件。

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
  profile.py
  pre_ss.py
  runtime_space.py
  number_ops.py

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

1. ~~固定本文档、`AGENTS.md`、`CLAUDE.md`、`todo.md` 中的目标结构。~~ ✅
2. ~~建立 compiler infrastructure 包：`diag/source/session/build/project/import_/analysis/debug/errors`。~~ ✅
3. ~~建立 VM 分层：`qy/backend/vm/spec/` 与 `qy/vm/instance/`。~~ ✅
4. ~~建立 `qy/std/` 目标包，停止新增 `qy/stdlib/` 文件。~~ ✅（功能全部迁入 `qy/std`，`qy/symbol_space/` 与 `qy/stdlib/` 兼容目录已删除）
5. ~~修复 `passes` 命名错位：`lower_mir.py` 必须是 HIR -> MIR，`lower_lir.py` 必须是 MIR -> LIR。~~ ✅
6. ~~解决同名 `macro`、`cli`、`errors` 冲突。~~ ✅
7. ~~解决 `ir/hir`、`ir/mir`、`ir/lir` 冲突。~~ ✅
8. ~~迁移 source/diag/session/project/import/build 的 legacy 文件。~~ ✅
9. ~~按 VM target spec / Python VM implementation 分层迁移 VM 文件，再删除 top-level 旧文件。~~ ✅
10. ~~迁移 CLI 到 `qy/cli/commands/`，再删除 `qy/cli.py`。~~ ✅
11. ~~迁移 stdlib 到 `qy/std/`，保留短期 `qy/stdlib` 兼容入口，最后删除。~~ ✅（兼容 shim 已删除）
12. ~~LIR effect lowering 接线 + VM 执行~~：`passes/lir/effects.py` 由 `lir.lower` 在 `PipelineOptions.lir_dialect == "abstract-machine"` 时调用；`passes/lir/spaces.py` 产出 `symbol_spaces` 并降成 `SS_*` / `SLOT_COMPLETE`。VM 现在执行 abstract-machine opcode（显式 handler 栈 + `QyContinuation` 快照；`CONT_RESTORE` 非终结），`tests/test_abstract_machine_vm.py` 与 compat 差分一致。默认执行路径仍为 `compat`。
13. 待推进：closure conversion、effect analyze / flatten、loop handling、CFG simplify、optimize passes 接入默认管线（当前 reg_alloc / cfg_simplify 会破坏 effect 程序，需先修复）。
14. 已完成：MIR 的 `ENTER_SCOPE`/`EXIT_SCOPE` 携带 program-level layout 的 space id（HIR `LetExpr`/`LambdaExpr`/`DefunExpr`/`ModuleExpr` 记录自身 space，`ProgramIR.root_space` 记录根 space），`passes/lir/spaces.py` 只查表不重建 layout，`LIRFunction` 不再有专属 layout 字段，`BytecodeProgram.symbol_spaces` 携带同一份事实；仍待推进：MIR 的 `DEFINE_ONCE`/`LOAD_ENV` operand 仍带 symbol 名（slot 由 `(space_id, symbol)` 查表得出，不是第二份 layout）；占位 pass 归属已收口（`raw.validate` / `resolve.spaces` / `effect.analyze` 实现并接入；重复占位已删除；仅 `closure.convert` 仍未实现）；abstract-machine 执行路径下 `TAIL_CALL` 跨 handle region 的 handler 栈保留。
15. 已完成：`qy check` 改为 canonical frontend + HIR verifier；HIR verifier 补 CallExpr 递归、effect 声明顺序跟踪、宏导出事实；`resolve.spaces` 实现为 HIR 层 symbol-space layout（`ProgramIR.symbol_spaces`，含 id/parent/slot/source），并**下沉到 MIR/LIR**（共享 `qy.ir.layout` 类型，见 `tests/test_resolve_spaces.py::test_layout_sinks_from_hir_to_mir_and_lir`）；清理死代码并补 `QY_DELETE_AFTER_*` 标记；`qy/sem` 不再反向依赖 `qy.vm`；LIR abstract-machine dialect 接线 + VM 执行；LLVM/WASM 验证后端可用。
