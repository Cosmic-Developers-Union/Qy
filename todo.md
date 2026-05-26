# Qy Full Roadmap

本文件不是最近一批工作的便签，而是 **Qy 从当前实现走到目标语言的完整路线图**。  
历史批次与已完成细节看 `report.md`；语言规范看 `LANGUAGE.md`；算子分层看 `docs/op.md`；阶段边界与 IR 约束看 `docs/pipeline.md`、`docs/ir-design.md`。

最近一次本地基线（2026-05-18）：

- `uv run python -m pytest -q`：363 passed
- `uv run ty check .`：passed
- `uv run python -m qy test.qy tests/qy`：40 / 40 passed

---

# 0. 最终目标

Qy 的目标不是“Python 上的一层 Lisp 语法”，而是：

- Python 实现的 like-Lisp 语言；
- 语言核心是：
  - everything is symbol；
  - syntax datum 只有 `symbol` 与不可变 `chain`；
  - 同一 symbol-space 内 symbol 不可重绑定；
  - algebraic effects；
  - register VM；
- 固定主管线：

```text
source
  -> raw AST
  -> surface dialect
  -> macro expand
  -> HIR
  -> MIR
  -> LIR
  -> bytecode
  -> register VM
```

- Python / Go 只是宿主与 adapter，不是语言语义本体；
- runtime value 是 Qy 语义对象，不能与 Python value 混淆；
- register VM 是唯一 runtime backend；
- 新能力默认先考虑能否由 Qy 自己实现，只有真正不可自举的能力才进入 host capability。

---

# 1. 不可漂移的语言契约

## 1.1 Syntax

- 语法只有 S-expression。
- raw AST / syntax datum 只能由：
  - `symbol`
  - immutable `chain` 构成。
- `form` 只是“一个 S-expression 单元”的叙述名，不是第三类语法对象。
- `chain` 不可变；`cons`、quasiquote、macro rewrite 都必须构造新 chain。
- `quote` 返回 syntax datum，不触发 runtime lookup。
- 默认 surface dialect 只做静态可描述的 spelling rewrite：
  - `'x -> (quote x)`
  - `` `x -> (quasiquote x)``
  - quasiquote 内 `,x -> (unquote x)`
  - quasiquote 内 `,@x -> (unquote-splicing x)`
- 不实现 unrestricted reader macro。

## 1.2 Runtime value

- runtime value 是 Qy 的语义对象。
- `nil` 与 `t` 是 Qy 自身对象。
- 抽象 runtime model 由：
  - `number`
  - `string`
  - `object` 构成；`number` 与 `string` 是特殊 object。
- Python value 只是宿主互操作对象，不能反向定义 Qy runtime model。
- host reference 是进入 Qy runtime 的语义对象；它可以指向 Python、Go 或其他宿主值。
- Python profile 可以显式暴露 `True` / `False` / `None` 等 Python value reference，但它们不等同于 `t` / `nil`。

## 1.3 Lookup 与 symbol-space

- 求值 symbol 时，沿 symbol-space-chain 顺序查找。
- 必须区分：
  - syntax symbol / datum symbol；
  - SymbolId / spelling identity；
  - binding address / slot；
  - completed runtime value。
- symbol-space 语义上是 `symbol -> binding slot`，lookup 返回 slot，读取 slot 才得到 value。
- binding slot 是 once-complete：可先由当前 symbol-space 声明并获得稳定地址，再按运行时求值顺序完成为 value；完成后不可同层再次完成。
- symbol-space 需要冷元数据层 / meta-space，保存 declaration span、export、operator metadata、hygiene/capture、debug 信息；value 热路径不应依赖 metadata record。
- `define`：
  - 只检查当前 symbol-space；
  - 构造一次性绑定；
  - 可以 shadow 后续链节点中的任意 symbol。
- `define` 只提升 binding，不提升 RHS 求值：
  - 分析/编译期扫描当前 lexical symbol-space 的直接定义；
  - 提前分配 binding slot，使 HIR 可解析前向引用；
  - RHS 仍按 `pipeline` / body 顺序运行；
  - 读取尚未完成的 slot 进入 pending-binding / incomplete-value effort。
- `let`：
  - 新建局部 symbol-space；
  - 可以绑定任意 symbol。
- `pre-symbol-space-chain`：
  - 不是语言理想本身；
  - 但它是标准实现围绕 `Qy` 实例展开的起点事实；
  - reader、analyzer、LSP、lowering、runtime 必须读取同一实例事实。
- chain 只描述 lookup；
- fold 才会把 binding 吸收到目标 symbol-space；
- `from` 是受 `exports` 约束的选择性 fold；
- module root 初始化也必须使用同一 chain + fold 模型。

## 1.4 Core operators

- `quote`
- `atom eq car cdr cons`
- `define let cond`
- `pipeline parallel all race`
- `defun lambda apply`
- `macro quasiquote unquote unquote-splicing gensym capture`
- `defeffect perform handle resume`
- `module from import exports`

说明：

- `cond` 只把 `nil` 视为 false。
- `truthy` 是 standard profile 的复杂真值判断算子，不改变 `cond`。
- `pipeline` 表示串行。
- `parallel` 只表示允许并行，不要求并行；支持 effect。
- `all` 是 barrier continuation。
- `race` 是 first-resume-wins。

## 1.5 Read / Eval / Reify

- `read: stream -> syntax datum`
- `eval: syntax datum + symbol-space-chain -> runtime value`
- `reify: runtime value + target context -> syntax datum`
- `reify` 是 partial operation：
  - 默认只要求“再次求值后得到等价值”；
  - identity round-trip 必须显式依赖 binding / handle / context；
  - host reference 必须显式实现 reify，或 `perform` reify effect 交给 handler。
- `display` / `write` / `reify` / `eval` 不能混为一类。

## 1.6 Runtime identity

- `eq` 最终必须比较 Qy runtime identity。
- Qy 不能依赖 Python `id()` / `is` 定义语言 identity。
- 若提供用户可见 `id`，其稳定范围由 Qy runtime 定义，不得泄漏宿主地址语义。

---

# 2. 当前现状

## 2.1 已完成

- register VM 已成为唯一公开执行路径；
- `qy.ir_vm/` 与 `python_codegen.py` 已删除；
- `raw AST -> surface dialect -> macro expand -> HIR -> MIR -> LIR -> bytecode -> VM` 主链已打通；
- `pipeline` / `parallel` / `all` / `race` / `apply` / effect 已进入主 pipeline；
- macroexpand 已独立，具备基础 hygiene、namespace、trace、source map；
- CLI 已支持：
  - `ast`
  - `expand`
  - `hir`
  - `mir`
  - `lir`
  - `bytecode`
- qytest 已形成一套行为验证集；
- examples 已分成 validation / design / host；
- `Environment.fold_from()` 已出现；
- `Qy.pre_symbol_space_chain` 已有只读快照；
- `evaluator.py` 已退出主求值路径。

## 2.2 仍在过渡

- raw AST 仍是 `Symbol | str | tuple[...]`，与目标 `symbol / immutable chain` 不一致；
- Python `str/int/list/tuple/dict/set/bool/None` 仍大量直接充当 runtime value；
- `eq` 仍由 Python `is` 支撑；
- `cond` / VM truthiness 仍受 Python 假值污染；
- `pre-symbol-space-chain` 仍更像展平 root + literal resolver；
- module / fold 存在多条近似实现路径；
- compile-time env 仍只是 runtime env facade；
- LIR 仍较薄，未完全承担低层职责；
- register VM 仍承担较多 host-call compatibility；
- `evaluator.py`、`eval_runtime.py`、legacy operator dispatch 仍活跃；
- `io`、`truthy`、runtime identity 仍未落地；`reify` 已有最小实现（partial、ScopeOperator、无 effect 路径）。

## 2.3 当前主要事实漂移

1. `reader.Form` 仍允许 Python `str` 与 tuple；
2. quoted literal 已在 reader 阶段变成 Python `str`；
3. `values.py` 里的 runtime `QyChain` 与 syntax tuple 并存；
4. `literal_resolver` 让 `1` 等 spelling 绕过了真正的 chain / fold 模型；
5. `(define 1 10)` 的行为尚未由最终 root 模型解释；
6. `qy.core` 仍混入 profile / compat 能力；
7. `qy.stdlib.data` 仍把 Python 容器视为一等目标语义；
8. `eq` 仍受 Python interning 影响；
9. `cond` 仍把 `False` / `None` / `()` 当作 false；
10. `truthy` 仅在文档中存在，尚无正式 operator；
11. `io` 仍只是 `print/echo` 模块，不是 Qy runtime model；
12. `reify` 已有最小实现（ScopeOperator、partial-failure、无 effect 路径）；
13. `HostObjectRef` 尚未演化成完整 host reference / runtime identity 容器；
14. compile-time namespace 仍未真正与 runtime namespace 分离；
15. `from` 在 stdlib / VM / source-module 路径没有完全共用实现；
16. `quasiquote` nested 路径仍依赖过时 `list/append` 假设；
17. LIR 目前仍与 bytecode opcode 基本同构；
18. LIR 尚未显式建模 virtual stack、continuation frame、handler frame、ss-chain transition、lookup operation、binding slot operation；
19. effect frame 仍主要由 VM 中的 Python 对象承担；
20. pending-binding / incomplete-value effort 尚未实现；
21. legacy `UserFunction` 仍让尾调用部分依赖旧 evaluator；
22. docs 中仍有少量旧说法需要持续清理。

---

# 3. 完成定义

只有同时满足以下条件，Qy 才算进入“架构闭合”状态：

- raw AST 真实只有 `symbol / chain`；
- runtime value 与 Python value 已严格分层；
- runtime identity 由 Qy 自己管理；
- `eq` / `cond` / `truthy` 按最新语义工作；
- `pre-symbol-space-chain` 是真实链，不是文档名词；
- `from` / module root / profile bootstrap 全部使用同一 fold primitive；
- macro 拥有真正 compile-time symbol-space；
- HIR / MIR / LIR 各自独立且有 verifier；
- LIR 已承担低层职责，bytecode compiler 只编码；
- register VM 不再依赖 legacy evaluator 承担核心语义；
- qytest 能覆盖语言契约；
- 文档、CLI、LSP、analyzer、runtime 读取同一事实源。

---

# 4. 完整推进路径

## Phase A0. 包结构收口（当前最高优先级）

当前目标是先保证目录结构和职责边界正确；测试失败可以后续处理，但不能继续让错误结构扩散。

### A0.1 目标结构真源

- 新增并维护 `docs/package-structure.md`，作为包结构真源；
- `AGENTS.md`、`CLAUDE.md`、`todo.md` 必须引用同一目标结构；
- 目标结构分两层：
  - compiler infrastructure：`diag/source/session/build/project/import_/analysis/debug/errors`；
  - language pipeline：`frontend/macro/core/sem/ir/passes/vm/backend/std/tools/cli`；
- VM 内部必须分层：
  - `qy/backend/vm/spec/`：VM target 规格，描述 bytecode/opcode/ABI/state/effect 协议；
  - `qy/vm/`：VM 的 Python 实现；
  - `qy/vm/instance/`：一次执行的可变 VM 实例，实现 spec，不定义 spec；
- 所有新增占位包必须使用中文 docstring 说明：
  - 目标；
  - 当前过渡状态；
  - 禁止承担的职责。

### A0.1.1 Compiler infrastructure 包

- `qy/diag/`：统一诊断系统，包含 `diagnostic.py`、`reporter.py`、`fixit.py`；
- `qy/source/`：源码与位置系统，包含 `file.py`、`span.py`、`sourcemap.py`；
- `qy/session/`：编译会话、配置、feature flags、profile facts，包含 `config.py`、`context.py`、`options.py`；
- `qy/build/`：pipeline driver、artifact、cache、build graph，包含 `pipeline.py`、`artifact.py`、`cache.py`、`graph.py`、`driver.py`；
- `qy/project/`：`qy.toml`、package、module、依赖与 source roots，包含 `manifest.py`、`package.py`、`module.py`；
- `qy/import_/`：module loader/import resolver/from-fold bridge，包含 `resolver.py`、`loader.py`；
- `qy/analysis/`：scope/ref/escape/liveness/effect analysis，包含 `scope.py`、`refs.py`、`escape.py`、`liveness.py`、`effects.py`；
- `qy/debug/`：IR dump、trace、VM debug、LLVM command log，包含 `dump.py`、`trace.py`、`vm.py`、`llvm.py`；
- `qy/errors/`：语言级异常、runtime error、compile error、internal compiler error 分类。

### A0.1.2 VM target spec / Python VM implementation

- `qy/backend/vm/spec/`：
  - `bytecode.py`：BytecodeProgram / BytecodeFunction / Instruction 规格；
  - `opcode.py`：opcode set、operand schema、register/branch/effect 约束；
  - `abi.py`：call ABI、frame ABI、handler/continuation ABI、host adapter ABI；
  - `state.py`：抽象 VM 状态契约；
  - `effect.py`：perform/handle/resume 的 VM 低层协议。
- `qy/vm/instance/`：
  - `machine.py`：RegisterVirtualMachine 实例与 dispatch loop；
  - `frame.py`：function frame、continuation frame、handler frame、task frame 的运行时对象；
  - `state.py`：pc、register file、frame stack、handler stack、pending task/effect；
  - `scheduler.py`：parallel/all/race 的调度、barrier continuation、first-resume-wins；
  - `host.py`：host reference/operator/capability adapter。
- 边界：
  - `backend/vm/spec` 是 VM target 的稳定契约，`qy/vm` 是 Python 实现；
  - instance 只能实现 spec，不得定义 opcode/ABI/operand schema；
  - bytecode emit 位于 `qy/backend/vm/emit.py`，只写入 spec 数据结构，不重新理解 HIR/MIR。

### A0.2 同名 module/package 冲突

不得长期同时保留 `name.py` 与 `name/`。迁移顺序：

- `qy/macro.py` -> `qy/macro/__init__.py`，随后删除旧文件；
- `qy/cli.py` -> `qy/cli/__init__.py` + `qy/cli/commands/*`，随后删除旧文件；
- `qy/errors.py` -> `qy/errors/__init__.py`，随后删除旧文件；
- `qy/ir.py` -> `qy/ir/__init__.py`，随后删除旧文件；
- `qy/mir.py` -> `qy/ir/mir/__init__.py`，随后删除旧文件；
- `qy/lir.py` -> `qy/ir/lir/__init__.py`，随后删除旧文件；
- `qy/ir/hir.py` -> `qy/ir/hir/__init__.py` / `node.py`，随后删除旧文件；
- `qy/ir/mir.py` -> `qy/ir/mir/__init__.py` / `node.py`，随后删除旧文件；
- `qy/ir/lir.py` -> `qy/ir/lir/__init__.py` / `node.py`，随后删除旧文件。

当前已知风险：

- `qy/macro/` 会遮蔽 `qy/macro.py`；需要保证 package 已暴露 `MacroDefinition` 等 public 类型；
- `qy/errors/` 会遮蔽 `qy/errors.py`；需要保证 package 已暴露全部 public error API；
- `qy/ir/lir/`、`qy/ir/mir/` 会遮蔽同名 `.py` 文件；搬迁完成前 import 可能失败；
- `qy/ir/hir/` 目前没有 `__init__.py`，一旦添加就会遮蔽 `qy/ir/hir.py`，必须同批迁入 public API。
- top-level `qy/lir.py` 当前仍可能遮蔽目标 LIR public API；`qy/__init__.py` 应改为从 `qy.ir.lir` 导入，或把 `qy/lir.py` 改成纯 re-export shim 后删除。
- `qy/cli/commands/*` 与 `qy/vm/{debug,emit,stack}.py` 仍有占位 docstring；若这些文件正在被他人修改，先不要抢写，实现完成后统一改成中文职责说明。
- `uv run qy --help` 当前仍可能触发 `qy/types.py` 遮蔽 stdlib `types` 的启动问题；`uv run python -m qy --help` 已能工作，console-script 包装需单独修。

### A0.2.1 删除计划

删除不是清理偏好，而是结构收口的完成条件。所有删除按前置条件推进：

标记规则：

- 迁移后删除文件使用 `QY_DELETE_AFTER_MIGRATION: target=...`。
- 语义替代后删除文件使用 `QY_DELETE_AFTER_SEMANTIC_REPLACEMENT: target=...`。
- 后续用 `rg QY_DELETE_AFTER qy` 审计待删范围。

- 可直接删除：
  - `qy/**/__pycache__/`
  - `.pytest_cache/`、`.ruff_cache/`、`.mypy_cache/`、`.ty/`
  - `QyLang.egg-info/`、`dist/`、packaging 临时 `build/`
  - `*.py.original`、`*.py.restored`
- 迁移后删除：
  - `qy/macro.py`
  - `qy/cli.py`
  - `qy/errors.py`
  - `qy/diagnostics.py`
  - `qy/reader.py` 或将其降为短期 public shim
  - `qy/ir.py`、`qy/mir.py`、`qy/lir.py`
  - `qy/ir/hir.py`、`qy/ir/mir.py`、`qy/ir/lir.py`
  - `qy/lowering.py`、`qy/mir_lowering.py`、`qy/lir_lowering.py`
  - `qy/bytecode.py`、`qy/bytecode_compiler.py`
  - `qy/register_vm.py`、`qy/virtual_stack.py`
  - `qy/analyzer.py`、`qy/formatter.py`、`qy/lsp.py`、`qy/benchmark.py`
  - `qy/source_modules.py`
  - `qy/llvm_codegen.py`
  - `qy/types.py`
- 语义替代后删除：
  - `qy/evaluator.py`
  - `qy/eval_runtime.py`、`qy/async_runtime.py`、`qy/symbol_utils.py`
  - `qy/operators.py`、`qy/operator_runtime.py`、`qy/operator_signature.py`、`qy/operator_docs.py`
  - `qy/runtime_values.py`、`qy/environment.py`、`qy/continuation.py`
  - `qy/values.py`、`qy/literals.py`、`qy/semantics.py`
  - `qy/stdlib/`

### A0.3 `stdlib` -> `std`

- 目标包名是 `qy/std/`；
- `qy/stdlib/` 是迁移期兼容目录，不得新增长期实现；
- docs 中可以暂时提到 `stdlib` 作为现状，但目标命名必须写作 `std`；
- `docs/stdlib-operators.md` 当前可保留文件名，后续重命名为 `docs/std-operators.md`。

### A0.4 Pass 命名修复

- `passes/` 按“阶段 + 主题”组织，不再继续平铺。
- 目标基础文件：
  - `pipeline.py`：pass 调度器，支持 dump/stop；
  - `pass_base.py`：Pass、PassContext、PassResult。
- 目标阶段目录：
  - `raw/validate.py`
  - `surface/normalize.py`
  - `macro/expand.py`、`macro/hygiene.py`
  - `core/desugar.py`、`core/validate.py`
  - `resolve/symbols.py`、`resolve/spaces.py`、`resolve/imports.py`
  - `hir/build_cfg.py`、`hir/validate.py`
  - `closure/convert.py`
  - `effect/lower.py`、`effect/analyze.py`、`effect/flatten.py`
  - `control/tailcall.py`、`control/loop.py`、`control/cfg_simplify.py`
  - `mir/normalize.py`、`mir/validate.py`
  - `lir/lower.py`、`lir/verify.py`、`lir/normalize.py`
  - `optimize/const_fold.py`、`optimize/dce.py`、`optimize/inline.py`
  - `emit/bytecode.py`、`emit/llvm_prepare.py`
- 旧文件标记为迁移后删除：
  - `qy/passes/lower_hir.py`
  - `qy/passes/lower_mir.py`
  - `qy/passes/lower_lir.py`
- 核心原则：
  - `ir/` 只放数据结构；
  - `passes/` 只放变换和分析；
  - `backend/` 只放目标后端输出。

目标 pass 顺序：

```text
raw.validate
-> surface.normalize
-> macro.expand
-> macro.hygiene
-> core.desugar
-> core.validate
-> resolve.imports
-> resolve.spaces
-> resolve.symbols
-> hir.build_cfg
-> hir.validate
-> closure.convert
-> effect.lower
-> effect.analyze
-> effect.flatten
-> control.tailcall
-> control.loop
-> control.cfg_simplify
-> mir.normalize
-> mir.validate
-> lir.lower
-> lir.verify
-> lir.normalize
-> optimize.const_fold / optimize.dce / optimize.inline
-> emit.bytecode 或 emit.llvm_prepare
-> backend
```

最重要的 pass：

- `resolve.spaces.py`
- `effect/analyze.py`
- `effect/flatten.py`
- `closure/convert.py`
- `lir/verify.py`

`pipeline.py` 必须支持：

```bash
qy emit main.qy --after=effect.flatten
qy emit main.qy --target=lir
```

### A0.5 VM / backend 边界

- `qy/backend/vm/` 是 VM target spec、bytecode emit、验证与适配的目标位置；
- `qy/backend/vm/spec/` 描述 VM 契约，可被 LIR lowering、bytecode verifier、Python VM implementation、LLVM/libqy validation 共用；
- `qy/vm/` 是 VM 的 Python 实现；
- `qy/vm/instance/` 保存一次运行的可变状态，不得反向污染 spec；
- `qy/backend/llvm/` 只作为 LIR 可靠性验证后端，不改变 register VM 是唯一主执行器的定位。

### A0.5.1 Project / package / import 边界

- `project` 只描述项目、包、模块、manifest 和依赖，不执行 pipeline；
- `import_` 解析 import spec 到 module/package/artifact，不直接求值 module body；
- `build.graph` 记录 module/package dependency graph；
- `build.pipeline` 串联阶段，但不实现阶段语义；
- `build.driver` 面向 CLI/API 组织 check/run/test/build。

### A0.6 完成标准

- 目标包均存在且有中文职责说明；
- 新代码不再写入待删 top-level legacy 文件；
- 同名 module/package 冲突全部消失；
- compiler infrastructure 包均存在，且与 language pipeline 包职责分离；
- VM target spec 与 Python VM implementation 已分离，且 instance 不定义 opcode/ABI 规格；
- 删除计划中的可直接删除项已清理，迁移后删除项不再被 public API 依赖；
- `qy/std/` 成为标准库目标包；
- `uv run python -c "import qy"` 恢复后，再进入语义修复和测试收口。

## Phase A. 文档与真源收口

### A1. 语言真源

- `LANGUAGE.md` 只描述稳定语言语义；
- `docs/op.md` 只描述 operator 分层与当前 operator 面；
- `docs/pipeline.md` 只描述阶段边界；
- `docs/ir-design.md` 只描述 HIR / MIR / LIR 的独立职责；
- `docs/package-structure.md` 只描述包结构和迁移边界；
- `docs/stdlib-operators.md` 当前只描述可变 std 草案，后续改名为 `docs/std-operators.md`；
- `docs/language-core-audit.md` 只描述实现偏移，不重复发明规范。

### A2. 说明文件一致性

- 保持以下文件同步：
  - `LANGUAGE.md`
  - `docs/op.md`
  - `docs/pipeline.md`
  - `docs/ir-design.md`
  - `docs/language-core-audit.md`
  - `AGENTS.md`
  - `CLAUDE.md`
  - `todo.md`
- 删除旧词：
  - `host value` 如果语义上指 runtime 对象，应改为 `host reference`
  - “Python 类型等于 Qy 类型”一类说法必须删除
  - 已移除的 backend / operator / form 不能残留

### A3. 报告制度

- 每批工作都写 `report.md`：
  - 目标；
  - 修改范围；
  - 新增 / 删除文件；
  - 复杂度变化；
  - 删除了哪些 legacy；
  - 引入了哪些新偏移；
  - 验证命令与结果。

---

## Phase B. Frontend：source -> raw AST -> surface dialect

### B1. raw AST 模型

- 把 raw AST 从 `Symbol | str | tuple` 收口为：
  - `Symbol`
  - immutable syntax `Chain`
- 删除 reader 阶段的 Python string 物化；
- 明确 syntax chain 与 runtime chain：
  - 是否同一数据结构；
  - 若不是，必须有严格边界与转换点；
  - 不允许长期存在“tuple AST + QyChain runtime”的混合模型。

### B2. literal spelling

- number / string / char spelling 在 raw AST 阶段仍只是 symbol 或受控 spelling；
- literal 解析只能发生在后续明确阶段；
- literal layer 必须属于 `pre-symbol-space-chain` 或显式 literal semantic pass，不能偷偷塞进 reader。

### B3. surface dialect

- 把 surface dialect 与 reader 本体真正拆开；
- 保留默认有限 sugar：
  - `'`
  - `` ` ``
  - `,`
  - `,@`
- binding / parameter 位置的 spelling rewrite 规则必须静态可知；
- analyzer、formatter、LSP、source map 共用同一 dialect 描述；
- 宿主可配置 dialect，但 Qy 源码不暴露 unrestricted reader macro。

### B4. source map / write / formatter

- `read_raw`、`surface dialect`、`macro expand` 都要保留可追踪 span；
- `write` 只处理 syntax datum，不承担 runtime `reify`；
- `display`、`write`、`reify` 的 API 与文档必须彻底拆开；
- formatter 只能操作 source/syntax 层，不得借 runtime 值判断。

### B5. 完成标准

- `qy ast` 输出只含 raw syntax model；
- raw AST 测试不再出现 Python `str` / tuple；
- reader、formatter、LSP 对同一 spelling 的理解一致；
- number/string spelling 的求值路径由实例链解释，而不是 reader 特判。

---

## Phase C. Runtime value / identity / truth / reify

### C1. runtime value 分层

- 建立 Qy runtime object model：
  - `nil`
  - `t`
  - `number`
  - `string`
  - `chain`
  - `array`
  - `hash-map`
  - `object`
  - `host reference`
- 固定 `number` 是 family、不是单一类型：
  - `int` 是任意精度整数；
  - `int32` / `int64` 是独立 concrete value type；
  - `float` / `float32` / `complex` / `rational` 也各自独立；
  - number family 内不做隐式 promotion，混合 concrete type 运算默认走 unsupported-operation effect / error；
- 明确 Python `int/str/list/...` 只是实现或 adapter；
- 决定：
  - `number` / `string` 是否拥有 Qy wrapper；
  - 它们如何携带 runtime identity；
  - 何时允许零拷贝接宿主实现。

### C2. runtime identity

- 设计 Qy 自己的 identity：
  - 分配规则；
  - 生命周期；
  - GC / reuse 约束；
  - host reference 的 identity 绑定；
  - singleton identity；
  - 是否对值类型做 interning。
- `eq` 改为比较 Qy identity；
- 删除依赖 Python small-int interning 的测试与语义；
- 若提供 `id`：
  - 定义其返回值类型；
  - 定义稳定范围；
  - 明确它不等于 Python `id()`。

### C3. truth model

- `cond` 只把 `nil` 当 false；
- 修改：
  - lowering / MIR / VM branch 语义；
  - legacy evaluator；
  - stdlib control；
  - tests；
- 实现 `truthy`：
  - 它是 standard profile 的复杂判断 operator；
  - 由它自己判断 Python reference、容器、数值、数组等广义真值；
  - 它返回 `t` / `nil`；
  - 不引入全局 Python truth coercion。
- 决定 `if` / `for` / `while` 是否建立在 `truthy` 上，还是继续保持各自显式规则。

### C4. reify

- 定义三种强度：
  - 可求值表示；
  - 等价回环；
  - identity 回环；
- 默认契约采用等价回环；
- identity 回环只允许通过：
  - symbol binding；
  - module reference；
  - handle；
  - 显式 context；
- host reference：
  - 必须显式实现 reify；
  - 或 `perform` reify effect；
  - handler 负责导出引用、构造表达式或拒绝；
- 明确 `read` / `write` / `display` / `reify` / `eval` 的关系；
- 设计可供 LSP / debugger / REPL 使用的最小 reify 能力。

### C5. 完成标准

- `eq` 结果与 Python interning 无关；
- `cond` 的真假只由 `nil` 决定；
- `truthy` 成为显式 operator；
- Python value 不再直接充当规范中的 Qy value；
- `reify` 拥有最小实现与 failure protocol。

---

## Phase D. Symbol-space / profile / module / fold

### D1. pre-symbol-space-chain 真模型

- 把当前展平 root 拆成明确链节点：
  - writable head；
  - core profile；
  - literal layer；
  - standard profile；
  - optional stdlib layer；
  - host injection layer；
- 每个节点明确：
  - lookup 可见性；
  - local membership；
  - 是否可写；
  - 是否 lazy；
  - 是否会被 root fold；
- reader、analyzer、LSP、lowering、runtime 读取同一个实例事实。

### D2. symbol-space / binding slot / meta-space

- 新增或重构正式 symbol-space 模型：
  - `SymbolId` / spelling identity；
  - `BindingAddr`；
  - `BindingSlot`；
  - `SymbolMeta`；
  - `SymbolSpace`；
  - `SymbolSpaceChain`。
- `SymbolSpace` 提供：
  - local lookup index；
  - slot storage；
  - metadata side table；
  - parent/chain linkage；
  - fold/import/export view；
  - debug/introspection dump。
- `BindingSlot` 至少表达：
  - declared；
  - computing / pending；
  - completed；
  - failed / poisoned（若 pending effort 未被处理或 RHS 失败）；
  - once-complete enforcement。
- 读取 pending slot 的行为必须走统一 pending-binding / incomplete-value effort，不得在 analyzer、lowering、VM 各自写错误分支。
- 明确 slot copy policy：
  - function closure 捕获；
  - module export；
  - continuation copy；
  - parallel branch；
  - host reference。
- 完成标准：
  - HIR resolved symbol 不再只是裸 `Symbol`；
  - VM 热路径可直接按 binding addr / slot 读；
  - metadata 可独立 dump，不污染 value layout。

### D3. define / shadow / fold

- 固定 root define 规则；
- 明确：
  - `(define 1 10)` 在默认 profile 下为何成功或失败；
  - 在 empty local symbol-space 中为何能 shadow；
- 固定 direct-definition hoist：
  - 每个 lexical symbol-space 进入前扫描直接 `define` / `defun` / `defeffect` / `macro`；
  - 同层重复定义在分析期诊断；
  - 只提升 binding slot；
  - 不提升 RHS 求值；
  - body 运行时顺序保持不变。
- 明确嵌套定义规则：
  - `cond` / `handle` / `parallel` / function body 内的定义只属于自身 lexical body；
  - 不允许 path-dependent define 穿透到外层 symbol-space；
  - 如未来需要动态 define，必须作为新算子重新设计，不得复用 `define`。
- 把 module root 初始化、profile bootstrap、`from` 全部表达成 fold；
- fold 只吸收 export view，不复制 namespace 背后的隐含 fallback；
- 冲突规则统一：
  - 同层已有本地 binding -> fail；
  - parent / later chain -> 可 shadow；
  - alias 冲突 -> 按当前层 define-once。

### D4. module

- `module` = 具名 symbol-space；
- `exports` = export view；
- `from` = selective fold；
- `import` = 命名/alias 语法；
- 统一三条实现路径：
  - stdlib module path；
  - register VM path；
  - source module provisional path；
- 宏导出与 runtime 导出必须有一致模型；
- 明确模块初始化时：
  - profile chain；
  - local root；
  - exported macro；
  - re-export；
  - repeated import；的规则。

### D5. profile

- 固定分层：
  - core built-in；
  - standard profile；
  - optional stdlib；
  - host capability；
  - compat layer；
- arithmetic、truthy、io、chain convenience 等都要明确归属；
- `qy.core` 只保留真正核心；
- `qy.py` 继续保持显式 opt-in；
- CLI `operators`、analyzer、LSP、runtime 使用同一 profile 描述。

### D6. 完成标准

- 同一 `Qy` 实例下，lookup / analyzer / LSP / runtime 全部一致；
- module / from / profile bootstrap 只剩一套 fold primitive；
- profile 差异可测试、可 introspect、可序列化说明。

---

## Phase E. Operator system

### E1. operator 分层

- core operator；
- standard built-in；
- optional stdlib operator；
- host capability operator；
- compat operator；
- 文档、metadata、runtime 三方一致。

### E2. operator metadata

- 固定 operator declaration schema：
  - name；
  - layer；
  - arity；
  - argument policy；
  - argument types；
  - rest type；
  - return type；
  - effects；
  - compile-time；
  - runtime-meta；
  - tail transparency；
  - docs；
  - source module / profile visibility；
- analyzer、LSP、CLI docs、lowering、runtime 统一读取；
- 不再让 `CORE_OPERATOR_SIGNATURES` / `STDLIB_OPERATOR_SIGNATURES` / 真实导出集合互相漂移。

### E3. custom operator

- 用户自定义 operator 必须能提供声明；
- 声明完整时：
  - analyzer 可做 arity / type / effect 检查；
  - LSP 可做 hover / completion / diagnostics；
  - lowering 可正确决定 argument policy；
- 声明不完整时：
  - 显式退化为 `unknown/any`；
  - 工具链不得从 Python 实现细节臆测语义。

### E4. core cleanup

- `qy.core` 只保留核心语义；
- `chain/append/get/has?/len/type/is` 等必须重新归层；
- `eval` 的层级必须重新确认：
  - 若它仍是 standard / meta 能力，不能偷留在 core；
  - 若它要进入 core，需要在 `LANGUAGE.md` 明确；
- `spawn` / `await` 保持移除；
- `defer` 保持移除，除非未来作为单独 meta/control 设计重开。

### E5. 完成标准

- 一个 operator 的语义只在一个声明源中定义；
- `operators` CLI 与 analyzer / runtime 输出一致；
- 自定义 operator 可以被 LSP 正确理解。

---

## Phase F. Macro system

### F1. compile-time symbol-space

- `compile_time_environment()` 不再只是 runtime env facade；
- 独立建模：
  - definition-site binding；
  - compile-time profile；
  - allowed capability；
  - effect policy；
  - module macro import/export；
- runtime namespace 不得无控制泄漏到 macro namespace。

### F2. hygiene

- 保持默认 hygienic；
- `capture` 作为唯一 intentional capture 路径；
- `gensym` 使用独立 identity；
- source map 必须可把展开结果追回：
  - call site；
  - definition site；
  - rename；
  - generated symbol。

### F3. quasiquote

- nested quasiquote 不得依赖过时 `list/append` 假设；
- quasiquote / unquote / unquote-splicing 的 lowering 只依赖稳定 core 面；
- macro 与 surface dialect 的责任严格分离。

### F4. diagnostics / tools

- expansion trace 可供：
  - CLI；
  - LSP；
  - diagnostics；
  - debugger；
- macro failure 必须带 compile-time stack 与 source map；
- qytest 覆盖：
  - hygiene；
  - capture；
  - gensym；
  - module macro import；
  - expansion failure；
  - source map。

### F5. 完成标准

- macro 不借 runtime env “顺手可用”；
- compile-time effect policy 可解释；
- hygiene 与 capture 可被 tools 正确展示。

---

## Phase G. HIR

完整要求见 `docs/ir-design.md`。这里列推进任务。

### G1. HIR 定位

- HIR 是 **高层语义 IR**；
- 它必须独立于：
  - surface dialect spelling；
  - raw AST 表示；
  - MIR CFG；
  - register VM；
  - Python host object layout。

### G2. HIR 必须表达

- resolved binding；
- stable binding address / slot ref；
- direct-definition hoist 之后的 symbol-space layout；
- pending binding read 的 effort fact；
- symbol-space 语义；
- operator declaration / signature；
- structured control；
- function / lambda；
- effect；
- module / fold；
- macro definition payload（仅在语义需要时携带 syntax datum）；
- source span；
- diagnostics；
- type/effect facts；
- tail-position facts；
- unresolved symbol as explicit node。

### G3. HIR 必须禁止

- raw tuple AST 泄漏；
- runtime `Environment` 对象引用；
- Python host value 直接作为语义；
- bytecode opcode；
- physical register；
- jump offset；
- hidden reliance on legacy `raw_args` compatibility。

### G4. HIR 需要补齐

- `BindingId` / stable binding reference；
- `BindingSlotRef` / `SymbolSpaceRef`；
- direct definition scan pass；
- pending-binding read node 或 effect fact；
- profile-aware resolved symbol info；
- runtime identity-independent literal representation；
- effect signature facts；
- operator declaration ref；
- verifier；
- dump 稳定格式；
- HIR-level tests；
- 删除 legacy `raw_args`；
- 明确 `eval`、`truthy`、future standard control 的 HIR 归属。

### G5. HIR 完成标准

- 给定 macroexpanded syntax + `Qy` instance facts，HIR 是确定的；
- HIR 不依赖 VM 就能被 analyzer / LSP 消费；
- HIR verifier 能拒绝：
  - 未声明但被当成 resolved 的 binding；
  - 非法 structured node；
  - 缺失 signature；
  - invalid span / effect facts。

---

## Phase H. MIR

### H1. MIR 定位

- MIR 是 **控制流与虚拟寄存器 IR**；
- 它必须独立于：
  - source spelling；
  - raw AST；
  - HIR 的树形便利；
  - physical register layout；
  - bytecode encoding；
  - host ABI。

### H2. MIR 必须表达

- CFG；
- basic block；
- virtual register；
- explicit evaluation order；
- branch / jump / return / tail call terminator；
- scope entry / exit；
- call；
- effect perform / handle / resume；
- handler region / marker；
- continuation edge；
- symbol-space-chain transition edge；
- binding slot read / complete；
- pending-binding effort edge；
- ordering/join semantics；
- module / fold operation；
- constant / binding references；
- source debug metadata。

### H3. MIR 必须禁止

- Environment lookup；
- runtime Python value 作为随意 payload；
- bytecode opcode 同构假设；
- physical register；
- final jump offset；
- structured control 仍以 HIR node 偷留；
- compile-time macro semantics。

### H4. MIR 需要补齐

- 真正的 constant reference / pool model，替代 `LOAD_HOST` 直接塞 Python object；
- explicit effect edges / handler regions；
- perform unwind edge；
- resume continuation 结构；
- ss-chain transition node / edge；
- binding slot op；
- pending-binding effort lowering；
- scope lifetime model；
- call convention abstract form；
- def-use verifier；
- CFG verifier；
- reachability；
- register liveness；
- tail-call verifier；
- dominance / ownership 规则（即使不采用 SSA，也要有明确 register 定义约束）；
- MIR pass pipeline：
  - canonicalize；
  - CFG simplify；
  - dead block cleanup；
  - constant / copy propagation（在 runtime model 稳定后）；
  - tail-position preservation。

### H5. MIR 完成标准

- HIR 的 structured semantics 已全部显式化为 MIR 控制流；
- MIR lowering 不依赖 Environment；
- MIR verifier 能独立发现非法 CFG、非法寄存器使用、非法 effect region；
- MIR dump 可直接解释程序控制流，不需要回看 HIR。

---

## Phase I. LIR

### I1. LIR 定位

- LIR 是 **Qy abstract machine IR**：低层、VM-facing、但尚未编码；
- 当前实现需要显式区分两个 dialect：
  - `compat`：迁移期保持现有 bytecode pipeline 可运行；
  - `abstract-machine`：目标 LIR，显式建模 virtual stack、continuation、handler、ss-chain、lookup、slot；
- `compat` 只能作为删除对象，不能继续承接新语义；
- 它必须独立于：
  - HIR；
  - MIR tree / CFG 结构；
  - bytecode binary/encoding 细节；
- 它不能再只是“共享 bytecode opcode 的线性 MIR”。

### I2. LIR 必须表达

- instruction selection 后的低层指令；
- scheduled / linearized block order；
- physical register layout 或明确 frame slot layout；
- calling convention；
- virtual stack frame；
- continuation frame；
- handler frame / effect marker；
- continuation capture / copy / restore；
- symbol-space-chain enter / leave / copy / restore；
- lookup operation；
- binding slot read / complete / pending effort；
- CFG space transition；
- effect dispatch / unwind；
- host-call ABI lowering；
- relocatable jump target / fixup；
- debug span / trace injection；
- constant pool reference；
- frame metadata；
- stack-map / continuation-map（若后续 GC / debugger 需要）。

### I3. LIR 必须禁止

- HIR node；
- MIR block semantic 依赖；
- Environment；
- source-level binding lookup；
- 语言级 `handle` / `perform` / `resume` 留壳；
- bytecode compiler 再次做高层决策；
- 与 bytecode opcode 一比一绑定到无法重写的程度。

### I4. LIR 需要补齐

- 自己的 opcode vocabulary；
- selection pass；
- block layout / rerank；
- register allocation / compaction；
- virtual stack frame lowering；
- handler frame lowering；
- continuation frame lowering；
- continuation copy / resume lowering；
- ss-chain transition lowering；
- lookup / slot operation lowering；
- effect unwind lowering；
- host ABI lowering；
- jump fixup；
- peephole；
- debug injection；
- verifier；
- textual dump；
- LIR pass ordering；
- LIR 与 bytecode 之间的 relocation / encoding boundary。

### I5. LIR 完成标准

- `LIR -> bytecode` 只剩 encode / pack / relocate；
- `handle` / `perform` / `resume` 不再作为 LIR 语言级 opcode 存在；
- effect frame 不再主要依赖 VM Python closure；
- continuation、handler、ss-chain、lookup、slot 全部在 LIR dump 中可见；
- host-call ABI 已在 LIR 层明确；
- 所有低层 rewrite 都能说清属于哪一个 LIR pass；
- LIR 可以为了不同 register VM 版本调整，而不需要回改 HIR / MIR。

---

## Phase J. Bytecode

### J1. bytecode 定位

- bytecode 是 register VM 的最终可执行表示；
- 它只消费 LIR；
- 它不重新理解：
  - binding；
  - effect；
  - module；
  - control；
  - profile；
  - host semantics。

### J2. 需要完成

- constant pool；
- function table；
- debug table；
- source map table；
- relocation 已闭合；
- validation；
- optional serialization format；
- versioning / compatibility strategy；
- bytecode dumper；
- round-trip test；
- invalid bytecode rejection。

### J3. 完成标准

- bytecode compiler 是结构转换器，不再含高层语义；
- register VM 可只看 bytecode 执行；
- bytecode dump 能与 LIR 对照验证。

---

## Phase K. Register VM

### K1. VM 定位

- 唯一执行器；
- 执行 bytecode；
- 不承担语言前端；
- 不承担 macro；
- 不承担 HIR/MIR 语义修补。

### K2. 必须完成

- 真 register execution；
- Qy runtime identity；
- virtual stack execution model；
- frame-carried symbol-space-chain；
- binding slot direct read / complete；
- pending-binding effort dispatch；
- frame layout；
- function call；
- tail call；
- continuation；
- effect frame；
- handler frame；
- ss-chain transition；
- `pipeline` / `parallel` / `all` / `race`；
- module / fold runtime operations；
- host-call ABI；
- error stack；
- debugger hooks；
- profiler hooks；
- GC / lifetime hooks（若对象模型需要）。

### K3. 当前需要迁移

- `_truthy` 改为 `nil` only；
- `_EffectFrame` 从 Python runtime detail 下沉到 LIR/bytecode model；
- `handle` / `perform` / `resume` 从 Python exception/closure 风格迁到 bytecode-visible virtual stack + ss-chain operation；
- `Environment.resolve` 热路径迁到 binding addr / slot read；
- host-call compatibility 缩到 adapter 层；
- `parallel` / `all` / `race` 的 continuation 与取消规则固定；
- mutual recursion TCO；
- effect boundary TCO；
- Python call stack 完全退出语义依赖；
- `UserFunction` 迁到 bytecode function；
- legacy operator dispatch 退出 core semantics。

### K4. 完成标准

- 新增核心语义不需要修改 evaluator；
- effect + tail call + parallel/join 能只从 bytecode 解释；
- VM 运行结果不依赖 Python interning / truthiness / callable semantics。

---

## Phase L. Legacy removal

### L1. evaluator

- `evaluator.py` 只能继续减，不能新增语义；
- 移除：
  - tail body path；
  - old effect continuation composition；
  - legacy truthiness；
  - compatibility exports；
- `eval_runtime.py` 最终降为零职责或删除。

### L2. legacy operator dispatch

- `PureOperator` / `ScopeOperator` / `ControlOperator` / `EffectOperator` / `MetaOperator` 最终只能保留为 host adapter，如无必要则删除；
- core semantics 全部走正式 IR / VM；
- stdlib 不再依赖 argument evaluator hack。

### L3. compat modules

- `qy.legacy` 仅用于迁移期；
- `spawn` / `await` / `component` 等不回流 core；
- 旧 `str-*` family 删除；
- 过渡 examples / tests 删除或迁到 compat test。

### L4. 完成标准

- 搜索 `qy.evaluator` 只剩历史文档或不存在；
- 新增 operator 不需要在 evaluator 与 VM 写两遍；
- legacy docs 完全隔离。

---

## Phase M. Standard profile / stdlib / host capability

### M1. standard profile

- 明确默认预装：
  - 哪些 core；
  - 哪些 standard built-in；
  - 哪些 literal layer；
  - 哪些 host capability；
- 默认 profile 不等于语言核；
- profile 可被实例化配置覆盖。

### M2. number

- 决定 number runtime model；
- 将 `qy/sem` 的 concrete number type 同步到 analyzer、LIR、libqy、LLVM ABI；
- 每个数值算子必须声明 concrete type signature；不得把 family membership 当成自动转换许可；
- 完成 `qy.num`：
  - host primitive；
  - Qy library；
  - equality；
  - comparison；
  - numeric tower；
  - numpy 互操作边界；
- arithmetic 是否默认加载必须由 profile 明确。

### M3. string

- 删除旧 `str-*`；
- 完成 `qy.str`：
  - runtime `string`；
  - host primitive；
  - Qy library；
  - Unicode policy；
  - string equality；
  - formatter / writer / display 分离。

### M4. io / fs / process / network

- `io` 是 Qy 自己的 runtime model，不是 Python file object 的别名；
- 先定义：
  - input stream；
  - output stream；
  - bidirectional stream；
  - byte stream；
  - char stream；
- 再定义 minimal capability：
  - read；
  - write；
  - flush；
  - close；
  - maybe seek；
- 分离：
  - `io`
  - `fs`
  - `process`
  - `network`
- Python / Go 只做 adapter；
- `echo` 若保留，应只是基于 `io` 的便利算子；
- 明确哪些 I/O 操作走 effect。

### M5. containers / object / struct

- 先固定底层值族：
  - `array` 是连续内存段，可取通用 `Value` cell 布局或 concrete value type 专门化布局；
  - `hash-map` 是 Qy 自有 hash/equality 规则下的映射结构；
- 再决定上层：
  - `list`
  - `tuple`
  - `set`
  - `dict`
  - `struct`
  - `object`
- 上层容器可以依赖 `array` / `hash-map`，但不得把底层值族和用户可见抽象混成一个概念；
- 决定 list / tuple / set / dict / struct / object 的 Qy 语义；
- 若它们只是 host adapter，不得伪装成语言基本类型；
- 若它们是正式 runtime family，必须：
  - 有 identity；
  - 有 type model；
  - 有 reify；
  - 有 operator family；
  - 有 analyzer support。

### M6. 完成标准

- standard profile 足够可用；
- stdlib 不是 Python helper 的随机集合；
- 宿主生态通过 adapter 进入，不反向决定语言结构。

---

## Phase N. Analyzer / LSP / CLI / formatter / tooling

### N1. analyzer

- 读取实例 profile / symbol-space-chain；
- 消费统一 operator declaration；
- 消费 HIR binding / type / effect facts；
- 支持：
  - unresolved symbol；
  - duplicate define；
  - arity；
  - type；
  - effect declaration；
  - module export/import；
  - macro diagnostics；
  - profile-specific symbols；
- 不自己发明 runtime truth 或 host type 规则。

### N2. LSP

- 基于具体 `Qy` 实例；
- completion / hover / diagnostics / rename 读取同一 metadata；
- 展示：
  - macro expansion；
  - hygiene rename；
  - source map；
  - operator signature；
  - module export；
  - profile visibility；
- 不把 Python 实现细节显示成 Qy 语义。

### N3. CLI

- 保持：
  - `ast`
  - `expand`
  - `hir`
  - `mir`
  - `lir`
  - `bytecode`
- 后续增加：
  - profile dump；
  - symbol-space-chain dump；
  - module export dump；
  - operator declaration dump；
  - macro trace；
  - maybe reify/debug tools。

### N4. formatter

- 只围绕 syntax；
- 与 surface dialect 同源；
- 不偷偷 normalize runtime value；
- 能 round-trip raw AST。

### N5. 完成标准

- analyzer / LSP / CLI / runtime 对同一实例的事实一致；
- 调试工具能观察每一层，不需要读 Python 源码猜。

---

## Phase O. Testing / examples / benchmarks

### O1. 测试分层

- `pytest`
  - 验证 Python 实现；
  - 验证每一编译层；
  - 验证 diagnostics；
  - 验证 regression；
- `qy test.qy tests/qy`
  - 验证语言行为契约；
  - 由 Qy 自己描述语言案例。

### O2. qytest

- 保持 host capability 最小：
  - read file；
  - list dir；
  - path；
  - args；
- assertion / reporting / DSL 尽量由 Qy 自举；
- 新增行为集：
  - raw AST；
  - nil-only cond；
  - truthy；
  - runtime identity；
  - reify；
  - profile；
  - pre-symbol-space-chain；
  - fold；
  - macro failure；
  - compile-time env；
  - io；
  - module conflict；
  - effect + parallel/race/all。

### O3. stage tests

- reader；
- surface dialect；
- macroexpand；
- HIR verifier；
- MIR verifier；
- LIR verifier；
- bytecode verifier；
- VM execution；
- analyzer；
- LSP；
- CLI；
- formatter；
- profile snapshot。

### O4. examples

- `validation/` 只保留当前可运行契约；
- `design/` 只描述未来目标；
- `host/` 展示 adapter 与 embedding；
- 删除解释旧实现的样例。

### O5. benchmarks

- 只保留 register VM 维度；
- workload 至少覆盖：
  - arithmetic；
  - recursion；
  - tail recursion；
  - module import；
  - macro heavy；
  - effect heavy；
  - string；
  - parallel/join；
- 记录：
  - parse；
  - surface；
  - expand；
  - HIR；
  - MIR；
  - LIR；
  - bytecode；
  - VM；
- 增加：
  - historical baseline；
  - regression threshold；
  - optional CI gate。

### O6. 完成标准

- 语言契约变化先改 qytest；
- 每一阶段有独立测试；
- benchmark 能解释性能回退来自哪个阶段。

---

## Phase P. Performance / optimization / diagnostics

### P1. front-end

- 缓存 source read / expand / lower；
- 避免重复全链路工作；
- macro cache；
- module cache；
- source map 成本监控。

### P2. HIR / MIR / LIR

- HIR：
  - binding pre-resolution；
  - constant binding fact；
  - effect fact；
- MIR：
  - CFG simplify；
  - dead block；
  - tail-call canonicalization；
  - liveness；
- LIR：
  - layout；
  - allocation；
  - rerank；
  - peephole；
  - debug injection switch；
- 所有优化必须能证明不越层。

### P3. VM

- frame allocation；
- environment allocation；
- tail-call frame reuse；
- continuation capture cost；
- host-call ABI；
- parallel scheduling cost；
- runtime identity allocation；
- constant pool。

### P4. diagnostics

- 每层错误都带 span；
- macro trace；
- virtual stack；
- effect stack；
- module path；
- profile info；
- source map；
- debugger 可解释 LIR / bytecode。

---

## Phase Q. Embedding / packaging / portability

### Q1. Qy instance API

- 自定义 profile；
- 注入 symbol-space-chain；
- 注册 custom operator；
- 注册 host reference adapter；
- 配置 surface dialect；
- 配置 macro capability；
- 配置 I/O / FS / process capability。

### Q2. portability

- Python backend 是当前实现；
- 语言模型不得依赖 Python：
  - truthiness；
  - identity；
  - object layout；
  - exception hierarchy；
  - file object；
- Go adapter / other host adapter 必须能复用同一 runtime model。

### Q3. packaging

- CLI；
- library API；
- VS Code extension；
- documentation；
- versioned bytecode；
- stdlib packaging；
- profile packaging。

---

# 5. 依赖顺序

以下顺序不建议打乱：

1. raw AST / syntax model；
2. runtime value / Python value 边界；
3. runtime identity + `eq` + `cond` + `truthy`；
4. pre-symbol-space-chain / profile / fold；
5. operator declaration；
6. macro compile-time env；
7. module path 统一；
8. HIR 收口；
9. MIR 收口；
10. LIR 真正独立；
11. VM effect frame / TCO；
12. legacy 删除；
13. stdlib / io / fs 扩张；
14. LLVM backend（Phase Q）**（新增，与 8–13 并行推进）**；
15. 性能优化与 portability。

原因：

- syntax 与 runtime model 不稳，后续 IR 会反复返工；
- symbol-space 不稳，analyzer / LSP / module / macro 都会漂；
- HIR 不稳，MIR/LIR 细化会建立在旧语义上；
- LIR 不独立，bytecode 与 VM 会继续吞掉本应属于 lowering 的职责；
- **LLVM backend 依赖 LIR 独立（LIR 不独立则 LLVM IR 无稳定输入），但与 legacy 删除、stdlib 扩张、VM 完善并行推进，互不阻塞。**

---

# 5½. LLVM Backend 完整设计

## 5½.1 架构定位

在现有管线旁边新增一条并行路径：

```text
source → raw AST → surface dialect → macro expand → HIR → MIR → LIR
                                                          ├──→ bytecode → register VM  (已有)
                                                          └──→ LLVM IR  → native binary  (新增)
```

LIR 是两条路径的分叉点，但 LLVM backend 不能依赖当前过渡期“近似 bytecode opcode”的 LIR。必须先完成 Phase I 的 Qy abstract machine LIR：virtual stack、continuation frame、handler frame、ss-chain transition、lookup、slot operation 全部显式后，LLVM codegen 才能把 verified LIR 当作稳定输入。

**设计约束**：

- LLVM backend 是并行验证路径，不是替换 register VM；
- 现有 `qy run` / `qy bytecode` / `qytest` 继续工作；
- 新增 `qy llvm` / `qy llvm --obj` / `qy llvm --exe`；
- 两套路径共享 LIR 作为输入，LIR verifier 保护两条路径；
- LLVM backend 必须消费新的 Qy abstract machine LIR，不得绕过 LIR 重新解释 HIR/MIR；
- 当前旧 LLVM 草案中的 `PERFORM` / `HANDLE` / `RESUME` 直接 runtime-call 映射只能作为历史 notes，不得作为实现计划。

## 5½.2 Qy Value → LLVM IR 类型映射

采用 **tagged pointer / discriminated union** 方案。最小可行子集必须跟 `qy/sem` value model 对齐，而不是直接复用 Python 旧 runtime。早期子集可以先覆盖：

```llvm
%qy_value = type { i8 tag, [7 x i8] payload }   ; 64-bit tagged union
```

| tag | 表示 | 备注 |
| --- | --- | --- |
| 0 | `nil` | Qy singleton |
| 1 | `t` | Qy singleton |
| 2 | `int64` | 机器整数；不等于任意精度 `int` |
| 3 | `int` | 任意精度整数，payload 指向 runtime object |
| 4 | `chain` | immutable chain cell |
| 5 | `string` | Qy runtime string |
| 6 | `function` | bytecode/native function ref + closure/ss-chain |
| 7 | `host reference` | 显式 adapter object |
| 8 | `array` | 连续内存段 |
| 9 | `hash-map` | Qy hash/equality 规则 |
| 10 | `continuation frame` | LIR 显式 continuation layout |
| 11 | `handler frame` | LIR 显式 handler/effect marker layout |
| 12 | `symbol-space frame` | LIR 显式 ss-chain frame/layout |

设计理由：

- tagged union 方案在 C 和 LLVM 中都自然；
- value layout 必须与 Qy 语义对象对齐，不与 Python dataclass 对齐；
- `perform` / `resume` 在 LLVM IR 层不是高层 runtime call，而是由 LIR 已经显式化的 continuation / handler / ss-chain operation 翻译而来；
- 未来扩层只需新增 tag。

## 5½.3 最小 C Runtime（MQR）

新建 `runtime/mqr.h` + `runtime/mqr.c`（约 100–150 行）。

核心 API（Phase 2 最少只需 6 个函数）：

```c
typedef struct { uint8_t tag; uint64_t payload; } qy_value;

// Tag accessors
static inline int qy_is_nil(qy_value v)   { return v.tag == 0; }
static inline int qy_is_T(qy_value v)     { return v.tag == 1; }
static inline int qy_is_int(qy_value v)   { return v.tag == 2; }
static inline int qy_is_cons(qy_value v)  { return v.tag == 3; }

// Constructors
qy_value qy_nil(void);          // tag=0, payload=0
qy_value qy_T(void);            // tag=1, payload=0
qy_value qy_int(int64_t n);     // tag=2, payload=n

// Arithmetic
int64_t  mqr_add(int64_t a, int64_t b);
int64_t  mqr_sub(int64_t a, int64_t b);
int64_t  mqr_mul(int64_t a, int64_t b);
int64_t  mqr_div(int64_t a, int64_t b);   // div-by-zero → effect
int64_t  mqr_mod(int64_t a, int64_t b);

// Comparison
qy_value mqr_eq(qy_value a, qy_value b);   // returns QY_T or QY_NIL
qy_value mqr_lt(qy_value a, qy_value b);
qy_value mqr_gt(qy_value a, qy_value b);

// Cons cell
qy_value mqr_cons(qy_value car, qy_value cdr);
qy_value mqr_car(qy_value c);
qy_value mqr_cdr(qy_value c);

// I/O
void mqr_print(qy_value v);
void mqr_println(qy_value v);
qy_value mqr_read(void);

// Abstract machine frames; exact API waits for Phase I LIR.
qy_value mqr_make_continuation_frame(/* layout decided by LIR */);
qy_value mqr_copy_continuation(qy_value frame);
qy_value mqr_make_handler_frame(/* layout decided by LIR */);
qy_value mqr_enter_ss_chain(qy_value ss_frame);
qy_value mqr_restore_ss_chain(qy_value ss_frame);

// Memory / GC
void* mqr_alloc(size_t size);
void  mqr_gc(void);

// String
qy_value mqr_make_string(const char* cstr, int64_t len);

// C runtime entry point
int64_t mqr_main(int64_t argc, char** argv);
```

## 5½.4 LIR → LLVM IR 翻译层

新建 `qy/llvm_codegen.py`（约 300 行）。

### 5½.4.1 指令映射

旧表中 `PERFORM` / `HANDLE` / `DEFINE_ONCE` 这类语言级 opcode 不能进入最终 LIR → LLVM 计划。新的映射表应在 Phase I 完成后重写，至少按这些类别组织：

| LIR 类别 | LLVM IR 对应 |
| --- | --- |
| value load | Qy value constructor / constant pool load |
| move / copy | register or stack slot load-store |
| branch / jump | LLVM basic block branch |
| call / tail call | ABI-lowered native call / musttail |
| slot read / complete | direct slot load-store + once-complete guard |
| pending-binding effort | branch to LIR-lowered effect dispatch path |
| ss-chain enter / leave / restore | explicit frame pointer / chain pointer operation |
| continuation capture / copy / restore | explicit frame record construction/copy |
| handler frame push / pop | explicit handler marker frame operation |
| effect unwind / dispatch | CFG jump sequence generated from LIR, not source-level `perform` |
| parallel/all/race join | task/join frame operation decided by LIR |

### 5½.4.2 函数映射约定

每个 `LIRFunction` 编译为 LLVM 函数：

```llvm
; 约定：所有 Qy 函数接受 (i64 argc, %qy_value* argv, %qy_env* env)
define %qy_value @qy.fn.{name}(i64 %argc, %qy_value* %argv, %qy_env* %env) {
entry:
  ; 参数映射：r0 = argv[0], r1 = argv[1], ... (由 caller 保证 argc 正确)
  %.r0 = load %qy_value, %qy_value* %argv
  ; ... function body ...
  ret %qy_value %.result
}
```

### 5½.4.3 llvmlite 集成

第一版用纯字符串模板生成 `.ll`，避免 llvmlite 版本绑定。第二版可迁移到 llvmlite 的 `ir.Builder`。

```python
# qy/llvm_codegen.py 核心结构
def emit_llvm_module(lir_program: LIRProgram, mqr_dir: str) -> str:
    """返回 LLVM IR .ll 文本（用于 qy llvm --ll）。"""

def compile_to_llvm_text(lir_program: LIRProgram, mqr_dir: str) -> str:
    """返回 LLVM IR .ll 文本（用于 qy llvm --ll）。"""

def compile_to_object(lir_program: LIRProgram, mqr_dir: str,
                      output_path: str, *, llc_path: str = "llc") -> None:
    """AOT 编译为 .o 文件（用于 qy llvm --obj）。"""

def compile_to_executable(lir_program: LIRProgram, mqr_dir: str,
                          output_path: str, *,
                          cc_path: str = "clang") -> None:
    """编译 + 链接为可执行文件（用于 qy llvm --exe）。"""
```

## 5½.5 CLI 集成

在 `qy/cli.py` 新增 `llvm` 子命令：

```bash
qy llvm FILE                  # 生成 LLVM IR 文本到 stdout
qy llvm --ll FILE            # 同上，显式 .ll 输出
qy llvm --obj FILE [-o OUT]  # 生成 .o 目标文件
qy llvm --exe FILE [-o OUT]  # 编译链接为可执行文件（默认 ./a.out）
qy llvm --run FILE           # 生成 + 立即运行（默认 ./tmp_qy_out）
```

若系统无 `clang`/`ld`，`--exe` 需显式指定 LLVM toolchain 路径（`--llc`, `--ld`）。

## 5½.6 实现顺序

```
Phase Q1: C Runtime 骨架
  → runtime/mqr.h + runtime/mqr.c
  → 验证：gcc -c runtime/mqr.c -o runtime/mqr.o && echo OK
  → 无任何 Python 依赖，纯 C 编译验证

Phase Q2: LIR → LLVM IR 翻译器（整数子集）
  → qy/llvm_codegen.py（emit LLVM IR 文本）
  → 前置：Phase I 的 Qy abstract machine LIR 已完成最小 value/slot/branch 子集
  → 验证：uv run qy llvm --ll examples/hello.qy → 输出 .ll
  → llc runtime/mqr.o program.ll -o program.o
  → clang runtime/mqr.o program.o -o program
  → ./program 对比 qy run FILE 输出

Phase Q3: 完善 value layout（cons cell、closure）
  → chain / function / ss-chain frame 映射
  → closure 捕获 binding slot / ss-chain ref，不捕获 Python env
  → 验证：qy llvm --exe core closure/chain qytest 子集 → 运行结果一致

Phase Q4: continuation / handler / ss-chain
  → 从 LIR 显式 continuation frame、handler frame、ss-chain transition 翻译到 LLVM IR
  → 不允许把 source-level PERFORM/HANDLE/RESUME 直接编译为 runtime call
  → 验证：qy llvm --exe tests/qy/29_nested_effects.qy → 运行结果一致

Phase Q5: 字符串、I/O、parallel
  → mqr_make_string / mqr_print / mqr_read 实现
  → PARALLEL_GATHER 用 pthread
  → 验证：qy llvm --exe tests/qy/27_all_barrier.qy → 运行结果一致

Phase Q6: GC / 优化
  → stop-and-copy GC（~50 行）
  → 寄存器分配器优化（线性扫描）
  → 验证：benchmark 对比 bytecode/register VM vs native
```

## 5½.7 完成标准

- Phase Q2 结束：整数子集 qytest 全部通过，LLVM 编译结果与 register VM 一致
- Phase Q3 结束：chain / closure / ss-chain ref 支持，语言核心子集完整
- Phase Q4 结束：continuation / handler / ss-chain operation 在 LLVM backend 下正常工作，且无语言级 PERFORM/HANDLE opcode 残留
- Phase Q5 结束：I/O 和并行能力在 LLVM backend 下正常工作
- Phase Q6 结束：可测量 benchmark，确认 LLVM backend 性能收益

---

# 6. 复杂度控制

当前冻结增长文件：

- `qy/lowering.py`
- `qy/analyzer.py`
- `qy/register_vm.py`
- `qy/mir.py`
- `qy/macroexpand.py`
- `qy/macro_hygiene.py`
- `qy/reader.py`
- `qy/evaluator.py`

规则：

- `evaluator.py` 只能减，不能加；
- 新语义不能同时落到 evaluator 与 VM 两套路径；
- 先拆真实边界，再加新分支；
- 新模块必须对应稳定概念，不得只搬运复杂度；
- 任何新增 host operator 都要回答：
  - 能否由 Qy 自己实现？
  - 属于 core / profile / stdlib / host capability 哪层？
  - metadata 是否完整？
  - 是否可被 analyzer / LSP 理解？

---

# 7. 删除清单

已删除：

- `qy.ir_vm/`
- `python_codegen.py`

必须继续删除或降级：

- `evaluator.py` 的剩余真实职责；
- `eval_runtime.py` 兼容面；
- legacy operator dispatch 对 core semantics 的承担；
- old `str-*`；
- `qy.legacy` 依赖；
- Python 容器伪装成语言核心类型的路径；
- Python `is` / truthiness 泄漏进语言语义的路径；
- 只验证旧过渡实现的 tests / examples；
- 与最新语言设计冲突的文档残留。

---

# 8. 验证矩阵

## 每批默认

```bash
uv run python -m pytest -q
uv run ty check .
uv run python -m qy test.qy tests/qy
```

## 触碰 frontend

```bash
uv run python -m pytest tests/test_reader_forms.py tests/test_reader_symbols.py tests/test_reader_write.py tests/test_formatter.py -q
```

## 触碰 macro

```bash
uv run python -m pytest tests/test_eval_macro.py tests/test_macroexpand.py tests/test_module_import.py -q
```

## 触碰 HIR / analyzer

```bash
uv run python -m pytest tests/test_ir.py tests/test_hir_nodes.py tests/test_analyzer_basic.py tests/test_analyzer_scope.py tests/test_analyzer_advanced.py -q
```

## 触碰 MIR / LIR / bytecode / VM

```bash
uv run python -m pytest tests/test_mir.py tests/test_lir.py tests/test_register_vm.py tests/test_register_vm_semantics.py tests/test_runtime.py -q
```

## 触碰 module / profile

```bash
uv run python -m pytest tests/test_environment.py tests/test_scope.py tests/test_module_import.py tests/test_binding_consistency.py tests/test_operator_signature.py -q
```

## 触碰 tooling

```bash
uv run python -m pytest tests/test_cli_commands.py tests/test_lsp.py tests/test_formatter.py -q
```

---

# 9. 近期执行序列

尽管本文件写的是完整路线，最近几批仍应按以下顺序推进：

1. **frontend 收口**
   - raw AST 改回 symbol / chain；
   - surface dialect 从 reader 中拆出；
   - writer / formatter 同步。
2. **runtime model 收口**
   - runtime value / Python value 分层；
   - Qy identity；
   - `eq`；
   - `cond`；
   - `truthy`。
3. **symbol-space 收口**
   - pre-symbol-space-chain 真模型；
   - fold / module / profile 统一。
4. **IR 文档落地为实现**
   - HIR binding ref；
   - MIR constant / effect region；
   - LIR 独立 opcode 与 low-level pass。
5. **legacy 清除**
   - `UserFunction` -> bytecode function；
   - evaluator 退场；
   - compat stdlib 下沉。

---

# 10. 结束条件

项目进入下一阶段前，至少应达到：

- 文档与实现不再分别描述两个语言；
- runtime object model 不再依赖 Python 偶然性质；
- IR 三层各自可独立解释、验证、演进；
- evaluator 不再承担核心语义；
- qytest 成为语言行为验收面；
- register VM 可以被视为真正唯一后端，而不是“主路径 + 旧解释器阴影”。
