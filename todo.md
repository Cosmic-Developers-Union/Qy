# Qy Full Roadmap

本文件不是最近一批工作的便签，而是 **Qy 从当前实现走到目标语言的完整路线图**。  
历史批次与已完成细节看本文档 §2 与 git log；语言规范看 `LANGUAGE.md`；算子分层看 `docs/op.md`；阶段边界与 IR 约束看 `docs/pipeline.md`、`docs/ir-design.md`。

最近一次本地基线（本轮整改后）：

- `uv run python -m pytest -q`：1056 passed, 1 skipped（skip 为 `QY_META_SELF=1` 才运行的自解释慢测试）
- `uv run ruff check .`：passed
- `uv run ruff format --check .`：passed
- `uv run ty check .`：**0 diagnostics**（本轮清空）
- `uv run qy check examples/qy/hello.qy`：ok（analyzer 已改为 canonical frontend + HIR verifier）
- HIR verifier 在 `examples/qy/hello.qy` 与 10 个 validation 样例上 clean（H1–H14）
- qytest `tests/qy` **56/56**、`examples/qy/validation` 10/10 通过；CLI 6 阶段 dump + run/fmt/export/llvm 全部可跑
- `make libqy` / `make llvm-gen` 可用；LLVM 原生链路实测可用（`examples/qy/validation` 4/10 走通并与 register VM 一致，其余为常量/未解析符号等已知限制，见 docs/llvm-backend.md）
- `qy/sem` 已不 import `qy.vm`；`UserFunction` 与 `qy/vm/instance/legacy_eval.py` 已删除，函数值统一为 `BytecodeFunctionValue`
- `rg QY_DELETE_AFTER qy`：7 处标记（stdlib shim、sem bridge、analysis infer/scope/refs、frontend tuple 兼容层）

历史基线（2026-09-14）：

- `uv run python -m pytest -q`：1048 passed, 1 skipped（skip 为 `QY_META_SELF=1` 才运行的自解释慢测试）
- `uv run ruff check .`：passed
- `uv run ruff format --check .`：passed
- `uv run ty check .`：48 diagnostics（`qy/cli/commands/pkg.py` 等既有问题，非本轮引入）
- 宿主边界：`qy/ext/` 扩展机制落地；`tests/test_extensions.py` 边界测试 7 项通过
- `meta-interp/cases/` 19 个自举用例与 `qy run` 参考输出逐字节一致；
  `tests/qy` 行为用例 **56/56**、`examples/qy/validation` 8 个验收样例全部对拍通过
- `meta-interp/main.qy` 已能解释自身源码（阶段 2 自解释），但性能很差（详见 §9½）
- **本轮语言修复**：H5 允许 let/handle body 尾调用；`type` 返回 Qy 语义类型名；
  dynamic call 允许 `any` 操作位；`qy run` 不再静默吞编译错误且退出码正确；
  `print` 不再重复求值 cons 结果；MIR→LIR `STORE_LOCAL` 寄存器重映射修复；
  参数列表 `(macro)` 不再被 macroexpander 误判为宏定义；
  `read-file`、`lookup-export`、`display`、`raise-error`、`gensym` 等 host 能力；
  自举解释器实现代数效应（CPS + 显式 handler/continuation）并覆盖并行/浮点/reify；
  host `eq` 对字符串字面量按值比较（对齐 LANGUAGE.md）；qy.num 新增 `string->number`；
  自举解释器补齐宏 hygiene（binder 重命名 + definition-site free symbol + capture/gensym）、
  dotted pair reader、multi-shot resume、算术算子的 identity-continuation 效应、
  `list`/`get`/`dict`、`bind`/`this`/`slot` 近似与 `(define 'name v)`。

历史基线（2026-08-02）：

- `uv run python -m pytest -q`：1011 passed（修复合并后的 `test_evaluates_target_file`
  与 `test_qytest_cli_entry_point` 两条 CLI 入口测试；详见 §A0.2.1 与 git log）
- `uv run ruff check .`：passed
- `uv run ty check .`：5 warnings（`click.core.Command` vs `click.Command` 类型差异，已知）
- `uv run python -m qy run test.qy tests/qy`：54 / 54 passed
- `git ls-files --others --exclude-standard`：空（cache / egg-info / dist 已清理）
- **新增发现**：`QyGroup.resolve_command` (`qy/cli/__init__.py`) 的 fallback 在
  typer 0.26.8 / click 8.4.2 下不再被触发 — parent `TyperGroup.resolve_command`
  对未知命令不再抛 `click.UsageError`，导致 `qy FILE` 隐式重定向是 dead code。
  推荐统一使用显式 `qy run FILE [ARGS]` 形式；fallback 的修复或删除作为单独议题。

历史基线（2026-06-09）：

- `uv run python -m pytest -q`：1011 passed
- `uv run ty check .`：passed
- `uv run python -m qy test.qy tests/qy`：54 / 54 passed

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
- `evaluator.py` 已退出主求值路径；
- `meta-interp/main.qy` 已形成可运行的 Qy-in-Qy 解释器，11 个用例与参考输出一致，
  阶段 2 自解释（解释自身源码）已打通（详见 §9½）。
- **本轮整改（analyzer / verifier / 边界）**：
  - `qy check` / LSP 诊断改为 canonical frontend（CST → surface → macro expand）+ `hir.lower` + H1–H14 verifier；analyzer 不再维护第二套语法/宏/作用域解释，`examples/hello.qy` 通过 `qy check`；
  - HIR verifier 修复 `_check` 不递归 `CallExpr` 参数导致的 H6/H7/H8 覆盖缺口；`defeffect` 声明改为按 body 顺序线程化；`on` 形式 handler 的自动声明 effect 不再误报；模块宏导出携带 `macro_exports` 事实，H3/H9 在宏-only 模块上不再误报；
  - `ty check .` 从 51 条收敛到 0（`is_chain` TypeGuard 化、`pkg.py` manifest 注解、`machine.py` 返回类型等）；
  - 删除死代码：`qy/backend/vm/optimize.py`、`qy/ir/hir/build.py`、`qy/passes/surface/normalize.py`、`_QyGroupFallback`；补 7 处 `QY_DELETE_AFTER_*` 标记；
  - `qy/sem` 不再 import `qy.vm`：legacy `UserFunction` / `ComponentOperator` 求值路径移至 `qy/vm/instance/legacy_eval.py`，`BytecodeFunctionValue` 用 `type_name="function"` 自描述；
  - Makefile LLVM 目标改指真实 `qy/resources/libqy`（原引用不存在的 `runtime/mqr.*` 与已删除的 `qy/llvm_codegen.py`）。
- **本轮整改（LIR abstract-machine 接线）**：
  - `PipelineOptions.lir_dialect` 选择 LIR dialect；`lir.lower` 在 `abstract-machine` 下调用 `lower_effects` 并填充 `frame_layout` / `handlers` / `continuations`（`qy/passes/lir/lower.py`）；
  - L5–L7 verifier 因此生效；L11/L12 改为 **CFG-aware** push/pop 配对（handler dispatch block 的深度由其 `HANDLER_PUSH` 播种），消除对合法 dispatch 路径的误报，同时保留真实 underflow / unclosed 检测；
  - `verify_lir` 的 "unreachable after terminator" 改为识别 block entry（jump / handler / continuation resume target），不再把 resume block 误判为不可达；
  - 新增 5 个测试（dialect 展开、underflow、unclosed、dispatch block、resume target）；`tests/test_lir.py` 37 passed。
- **本轮整改（LIR symbol-space / slot）**：
  - 新增 `qy/passes/lir/spaces.py::assign_symbol_spaces`：按线性 scope 栈把 `ENTER_SCOPE`/`EXIT_SCOPE`/`DEFINE_ONCE` 降成 `SS_ENTER`/`SS_LEAVE`/`SLOT_COMPLETE`，并产出 `LIRFunction.symbol_spaces`；
  - 修正 `SLOT_COMPLETE` operand schema 为 `(LIRBindingAddr, src_reg)`，L9 由恒空变为真实检查，且 slot identity 改为**按函数**比较（修复跨函数 `(0,0)` 误报）；L8 现在校验 slot address 指向存在的 space；
  - L10 同时检查 compat 的 `ENTER_SCOPE/EXIT_SCOPE` 与 abstract-machine 的 `SS_ENTER/SS_LEAVE`，并保持 warning 严重级；
  - 新增 4 个测试（layout/ops 产出、重复 SLOT_COMPLETE、函数局部 slot identity、space 越界）；全量 1065 passed。
- **本轮新增（WebAssembly 后端）**：
  - `qy/backend/wasm/`（`abi.py` 值编码 + `emit.py` LIR→WAT）+ `qy/resources/wasm/runtime.js`（JS 宿主 runtime）+ `qy wasm` CLI；
  - 每个 LIR function 编成一个 wasm function，统一签名 `(argc i32, argv i32) -> i64`，内建算子走函数表 trampoline + `call_indirect`；扁平 CFG 用 `loop`/`br_table` dispatcher；
  - 符号在编译期解析，env 绑定快照进专用局部变量（避免寄存器复用覆盖）；缺失符号抛 `WasmUnsupportedError` 而非静默错误编译；
  - 端到端验证（`wat2wasm` + Node）：`00_host_arithmetic`、`02_symbol_space_let`、`03_functions_tail_call`、`09_register_vm_tail_call` 与 register VM 结果一致；`tests/test_wasm_backend.py` 9 passed；
  - 文档 `docs/wasm-backend.md`（已注册到 `docs/README.md`）。
- **本轮新增（HIR `resolve.spaces`）**：
  - `hir.lower` 现在把 symbol→slot 写入 `SymbolSpace.bindings`，并记录 `sources`（冷元数据）；`DefineExpr` / `DefunExpr` 记录 `owner_space`；
  - 新增 `qy/passes/resolve/spaces.py::ResolveSpacesPass`：收集 lowering 期创建的 lexical space，分配稳定 id、parent 链与 slot（symbol/index/source），产出 `HIRSymbolSpaceLayout` 并挂到 `ProgramIR.symbol_spaces`；profile 预装空间（只含 `builtin` 绑定）被过滤；
  - 默认管线加入 `resolve.spaces`（`hir.lower` 之后、`hir.validate` 之前）；`hir.validate` 现在保留 `symbol_spaces`；
  - `tests/test_resolve_spaces.py` 6 passed；全量 1087 passed。
  - 仍待推进：MIR 指令携带 binding id/slot，LIR 才能消费 HIR layout 而不是重建。
- **本轮新增（VM 执行 abstract-machine opcode）**：
  - `backend/vm/spec/opcode.py` 与 `backend/vm/bytecode.py` 的 opcode 集加入 `SS_ENTER/SS_LEAVE/SLOT_COMPLETE/HANDLER_PUSH/HANDLER_POP/EFFECT_UNWIND/EFFECT_DISPATCH/CONT_CAPTURE/CONT_COPY/CONT_RESTORE`；`compile_lir_bytecode` 接受 `abstract-machine` dialect，并把 `LIRFunction.symbol_spaces` 带到 `BytecodeFunction`；
  - `_Frame` 增加显式 `handlers` 栈与 `pending_effect`；`EFFECT_UNWIND` 抛 signal，持有 `HANDLER_PUSH` 的 frame 在 `CALL` 处捕获并跳 dispatch block；`EFFECT_DISPATCH` 写回 handler fn/arg/continuation；`CONT_CAPTURE` 用不可变快照（multi-shot 天然成立），`CONT_COPY` 别名，`CONT_RESTORE` **非终结**（写回 dst 后继续）；
  - 修正 `CONT_RESTORE` 被当作 terminator 的问题（`verify.py`/`lir/predicates.py`/spec 同步）；否则 `(+ (resume k a) (resume k b))` 组合 resume 会丢第一次 resume；
  - `tests/test_abstract_machine_vm.py`：多 shot、non-resumable、无 resume、嵌套 handler，以及 hello + 全部 validation 样例的 compat/abstract-machine 差分；全量 1097 passed；
  - compat dialect 仍拒绝 abstract-machine opcode；默认执行路径仍是 compat。
- **本轮新增（layout 下沉 HIR → MIR → LIR）**：
  - 新增中性类型 `qy/ir/layout.py`（`BindingSlot` / `SymbolSpaceLayout`），HIR 的 `HIRBindingSlot` / `HIRSymbolSpaceLayout` 改为其别名；
  - `MIRProgram` / `LIRProgram` 增加 `symbol_spaces`；`mir.lower` 从 `ProgramIR` 携带，`mir.validate`、`lir.lower`、`lir.verify` 逐级保留；
  - `tests/test_resolve_spaces.py::test_layout_sinks_from_hir_to_mir_and_lir` 断言 HIR == MIR == LIR；
  - 仍待推进：MIR 指令 operand 直接携带 binding id/slot（现仍只带 symbol 名，LIR `SLOT_COMPLETE` 地址由 `passes/lir/spaces.py` 重建）。
- **本轮整改（值模型 / syntax datum / literal / std / CLI / 死代码）**：
  - 值模型收口：`qy.core.syntax` 成为 `Symbol` / `Chain` / `QyNil` / `Form` / `get_span` 与
    Qy 自身对象 `nil` / `T` / `none` 的唯一真源；删除 `qy.sem` 重复 datum
    （`DatumValue`/`SymbolValue`/`NilValue`/`ChainValue`）与 `qy.sem.bridge`；
  - raw AST 收口：删除 `qy/frontend/form.py` 与 tuple 兼容 API
    （`form_to_tuple`/`read_tuple`/`write_tuple`/`TupleForm`/`SpannedTuple`/`DottedTuple` 等），
    `Form = Symbol | Chain | QyNil`；`surface.py` 的 tuple 版实现删除；
    `macro/hygiene.py` 改为 chain 表示并保留 span；
  - quasiquote 展开统一到 `qy/core/quasiquote.py`，macro expand 与 HIR lowering 共用；
  - literal 不再物化：`try_default_literal` 返回 `IntValue`/`FloatValue`，
    MIR quote 不再把字符串 spelling 解成宿主 `str`（`quote` 一律返回 syntax datum）；
  - 修复 VM `runtime eval`：`machine._eval_form` 不再把 Chain 转成宿主 tuple 后入管线；
  - 标准库收口：`qy/symbol_space/*` 全部迁入 `qy/std/*`，删除 `qy/symbol_space` 与 `qy/stdlib`；
  - CLI：`main()` 统一处理 click usage error（不再抛裸 traceback）；
    `ast`/`run`/`fmt`/`check`/`typecheck` 支持 `-` stdin；`completion` 从真实 group
    派生命令清单（修复漏 `pkg`）；`pkg publish` / `pkg update` 无 registry 时显式失败；
  - 占位 pass 收口：实现 `raw.validate`（raw AST 只能是 symbol/chain/nil）与
    `effect.analyze`（declared/performed/handled/escaping/discarded/multi-shot/parallel
    事实 + EA1 hint），两者接入默认管线；删除 10 个已被现有实现覆盖的重复占位
    （`macro/hygiene`、`core/desugar`、`core/validate`、`resolve/{symbols,imports}`、
    `control/loop`、`lir/normalize`、`emit/llvm_prepare`、`effect/{lower,flatten}`）
    与空的 `passes/surface/`；空占位 `closure/convert.py` 与 `qy/tools/lint/` 后续
    也已删除——closure 模型由 `hir.lower`/`mir.normalize`/VM 承担，再开 pass 会形成
    第二份语义，当前**没有未实现 pass**；
  - 优化接线：`PipelineOptions.optimize` + `optimize.mir` 接线点接入默认管线
    （默认 False），优化顺序真源收敛到 `passes/optimize/apply.py::OPTIMIZE_PASSES`；
    （**已作废**：round 1 的 46/86 是度量假象——repr 含内存地址、pass name 重复导致
    子集选错；round 3-5 修正口径并修复缺陷后，86 语料在 S1-S5 全部子集下与未优化结果
    一致，`optimize` 已默认开启，证据见 docs/package-structure.md §3.1 与
    `scripts/optimize_frontier.py`。）原计划接下来是让
    optimize pass 正确处理 language-level effect / continuation 控制流。
  - legacy 分阶段退役（第一步）：`qy/macro/evaluator.py` 不再导入
    `qy.vm.instance.frame.QyContinuation` 与 `legacy_eval`（编译期 effect 用本地
    `_CompileTimeContinuation`，UserFunction/ComponentOperator 在编译期环境自行求值），
    `qy/macro/` 已不依赖 `qy.vm`；`PureOperator`/`ScopeOperator`/`ControlOperator`/
    `EffectOperator`/`MetaOperator` 不再从 `qy` 顶层导出（内部位置 `qy.core.operators`），
    `Qy.register_*` 明确标注为 legacy operator dispatch 兼容入口；
  - layout 下沉补链：`BytecodeProgram.symbol_spaces` 携带 HIR 下沉的程序级 layout，
    不再在 backend 边界丢失（`BytecodeFunction.symbol_spaces` 类型收紧为
    `LIRSymbolSpaceLayout`）；剩余差距是 MIR operand 携带 binding id/slot；
  - LSP 事实源同步：新增 `qy/tools/lsp/facts.py`（canonical frontend + HIR）；
    completion 与 hover 现在读取与 `qy check`/analyzer 相同的 HIR 事实，
    能识别 `define`/`let`/参数/handler 参数/`defeffect` 等 lexical binding
    （此前只读 surface forms、看不到局部与宏展开后的定义）；新增
    `qy/tools/lsp/navigation.py` 并注册 `textDocument/definition` 与
    `textDocument/references`（基于同一份 HIR symbol occurrence 事实）；
  - 目标完成状态（本轮汇总）：objective 的九项均已落地并有验证证据——
    缺陷修复、legacy/失效代码删除（legacy_eval/UserFunction/ComponentOperator/
    空占位/死分析/stdlib shim/tuple 兼容层）、未实现 pass 与语义（当前无未实现
    pass）、runtime value 模型 / binding layout / 算子分发各自收口到单一事实源，
    文档 / CLI / LSP / 测试逐项同步。剩余为**增量扩展**而非结构债，另列于此：
    1) 其余非内建算子若需要 VM 快路径，按同一模板扩充 `operator_builtins` 与
       三后端实现（VM 取用既有 body、wasm/llvm 各自实现）；
    2) continuation `saved_registers` 由保守全集精化为活跃区间（LIR 侧）；
    3) `qy lint` 若要成为产品能力，需先定义规则集（当前静态检查入口为 `qy check`）；
    4) compile-time namespace 的一般化（宏体在编译期调用 module-local defun
       目前给出明确诊断而非支持）。
  - 内建算子表收口（单一事实源）：原先 wasm ABI、llvm ABI 与 wasm 宿主 runtime
    三处各写一份内建算子名字/元数/下标顺序，靠注释手工同步；新增
    `qy/core/operator_builtins.py`（BuiltinOperator: name/arity/runtime_symbol）作为
    唯一事实源，两个后端 ABI 派生，并新增 `tests/test_operator_builtins.py` 守卫
    （含解析 `qy/resources/wasm/runtime.js` 的 `/* N name */` 注释核对宿主侧顺序、
    内建 ABI 元数落在算子声明元数区间内）。
  - 算子分发迁移（选项 A，已落地）：新增字节码/ LIR `CALL_BUILTIN` + LIR selection
    （`lir.select_builtins`，默认管线接入）+ VM 内建实现表（取用 `qy.std`/`qy.session`
    同一批 body，不复制语义）+ wasm/llvm 消费同一下标；顺带消除
    `qy/backend/vm/bytecode.py` 里第二份 `Opcode` 列表（现从 spec 重导出）。
    负例守卫：shadow、宿主覆盖、效果/作用域算子、元数不匹配、非法下标。
    剩余：其余算子若需要同类快路径，只需扩充 `operator_builtins` 与三后端实现。
  - legacy 求值路径删除（P1-2 收尾）：`qy/vm/instance/legacy_eval.py` 与
    `qy/sem/runtime.py::UserFunction` 删除，函数值统一为管线编译的
    `BytecodeFunctionValue`。module-local defun 改两阶段预置（compile-time
    `MacroFunction` 占位 + 管线编译的运行期值），F1（导出宏引用未导出 helper）
    仍通过；`project/module.py` 的 provisional 占位改为 `ProvisionalFunction` 标记。
    代价：宏体编译期调用 module-local defun 现在给出明确诊断。测试净减 11 条
    （legacy TCO / UserFunction 单测），全量 1126 passed。
  - 优化默认开启（P2-1）：S1-S5 全语料一致 + 全量 pytest/qytest/abstract-machine
    差分全绿后，`PipelineOptions.optimize` 默认改为 True。开启前补齐：`const_fold`
    只折叠语言实现算子（宿主 `register_pure` 函数不再在编译期执行）、
    `qy/backend/scalars.py` 统一后端常量分类（wasm 不再报 unsupported、llvm 不再
    静默 nil）。收益：指令 -16% / 寄存器 -58% / fib(18) -7% / 编译 +10%。
    已知边界：llvm 不支持 char/float 常量（显式报错），wasm 不支持 float。
  - 优化正确性（第三批）：effect 重编号与内联健全性收口（见
    `docs/package-structure.md` §3.1）。`EFFECT_RESUME(dst, cont, value)` 的 value
    寄存器此前未被 `reg_alloc` 重编号（resume 传回陈旧值）；
    `optimize.inline` / `aggressive_inline` 各自复制了一份实现且都缺闭包守卫
    （闭包变量被内联 → `unresolved symbol`）、形参未替换为实参寄存器、`_offset_instruction`
    兜底给所有 int 操作数加偏移、effect 守卫写的是不存在的 opcode；现两份实现收口到
    `passes/optimize/inline_core.py`。另外修掉：`const_prop` 未核对宿主 env 覆盖、
    `reg_alloc` 未映射无活跃区间的寄存器（LIR out-of-range）、位置参数重建
    `MIRFunction` 丢掉 `space_id`（LIR 不再发 `SLOT_COMPLETE`）、`instr_sched` 丢
    `LIRProgram.symbol_spaces`。实测 86 语料在 S1-S5 全部子集下与未优化结果一致
    （`scripts/optimize_frontier.py`），收益 -16% 指令 / -58% 寄存器；默认开启仍有
    14 个测试失败（llvm/wasm 后端常量形态 9、async core 3、开关断言 2），
    已记入 §3.1，留给下一轮。
  - 优化 pass 正确性（第二批）：CFG/活跃区间/寄存器表收口。`cfg_simplify` /
    `licm` / `loop_opt` / `analysis.liveness` 各自复制了一份只认 JUMP/BRANCH 的 CFG
    后继，都把 `EFFECT_PERFORM` 的 resume 块当不可达；现统一到
    `qy.ir.mir.terminator_targets` / `terminator_target_positions`。liveness 从未收集
    terminator 的寄存器使用，`reg_alloc` 手写 per-opcode 重映射且漏项；现在
    `qy.ir.mir` 提供唯一的寄存器表（`register_operand_positions` /
    `register_def_position` / `terminator_*`）供 liveness 与 reg_alloc 共用。
    `intern` 不再按 `hash` 去重（`T`/`none` 同为 `hash(())`）也不再合并 identity
    可观察的 symbol/字符串常量。实测 S3 11/86→0/86、S5 42/86→11/86；
    剩余：S5 的 11 个失败全部是 effect 语料（疑似 continuation 保存寄存器集合
    与合并后的活跃区间不一致，LIR 侧 `saved_registers=tuple(range(register_count))`
    仍是保守全集），下一轮定位；S4 仅剩 1 个 inline 语料。
  - 优化 pass 正确性（第一批）：修复 `const_prop` 的两个缺陷（把 CALL 参数寄存器号
    替换成常量池下标 → 运行期读错寄存器；未排除被 shadow 的字面量/算子名，且文档承诺的
    `LOAD_ENV` 字面量降级从未实现）与 `const_fold` 的两个缺陷（shadow 的算子名仍按内置
    算子折叠；用跨块"最后一次写寄存器"当定义，不支配使用点），并让所有 optimize/control
    pass 经 `passes/optimize/facts.rebuild_program` 保留 `symbol_spaces`；
    新增 `scripts/optimize_frontier.py`（子进程隔离 + 结果规范化的可复现测量）；
    实测 S1/S2 从 11/86 降到 **0/86**，S5 从 42/86 降到 33/86；
  - 仓库工具隐患：`.gitignore` 的 `instance/` 未锚定会匹配 `qy/vm/instance/`，
    导致 ripgrep 递归搜索时静默跳过该子树（git 自身对被跟踪文件不判 ignore，
    所以不易察觉）；已改为 `/instance/` 并新增守卫测试
    `test_rg_sees_every_tracked_qy_source_file`（rg 可见文件集必须覆盖全部已跟踪
    `qy/**.py`）；AGENTS.md 记录 `rg --no-ignore` 复核建议；
  - compile-time 函数值：新增 `qy.macro.MacroFunction`，编译期求值器自行处理
    `lambda` / `defun`（不再经过运行期算子），修复了 round 1 引入的两处回归
    （macro body 内的 `(lambda ...)` 与 `(defun ...)` + 调用此前会得到 VM 函数值
    而无法在编译期调用）；编译期调用 VM 函数值现在给出明确诊断而不是静默失败；
    仍待推进：`macro/expand.py::_prepopulate_module_locals` 的 module-local 占位仍需
    "运行时可调用"，暂时继续使用 legacy `UserFunction`（见 §2.3 第 21 条）；
  - legacy 分阶段退役（第二步）：`qy.std.control` 的 `lambda` / `defun` 算子
    （值位置路径，如 `(apply lambda '((x) ...))`）改为经完整管线编成
    `BytecodeFunctionValue`，不再构造 legacy `UserFunction`；实测语料中
    `legacy_eval.call_user_function` / `call_component_operator` 调用次数为 0，
    剩余 `UserFunction` 生产者只有 macro 编译期环境（由编译期求值器执行，不走 VM）
    与 `project/module.py` 的元数据占位；`legacy_eval` 与 VM 分支待 macro
    compile-time namespace 落地后再删除；
  - layout 单一事实源：HIR `LetExpr`/`LambdaExpr`/`DefunExpr`/`ModuleExpr` 记录自身
    symbol-space，`ProgramIR.root_space` 记录根 space；`resolve.spaces` 的 space 枚举
    与 id 映射共用同一实现（`collect_space_ids`）；MIR 的 `ENTER_SCOPE`/`EXIT_SCOPE`
    携带 layout space id；`passes/lir/spaces.py` 只按 program-level layout 查表把
    `DEFINE_ONCE` 改写为 `SLOT_COMPLETE`，不再 per-function 重建 layout；
    `LIRFunction` 删除专属 layout 字段，删除未产出的 LIR slot 模型类型
    （`LIRSymbolSpaceLayout`/`LIRBindingSlot`/`LIRSymbolMeta`/`LIRBindingState`）；
    L8 改为按 program-level layout 校验 address，L9 收紧为 program-wide slot identity；
    compat 与 abstract-machine 在 86 个语料上语义结果逐一致（diffs=0）；
  - 死代码清理：删除 `vm/instance/{scheduler,host}.py`、`session/options.py`、
    `analysis/{infer,scope,refs,escape,effects}.py`、`sem.host.HostObjectRef` 别名、
    根目录过期 demo（`component_demo.qy`/`test-cov.qy`）；`roadmap.yaml` 迁入 `docs/` 并注册。

## 2.2 仍在过渡

- Python `str/int/list/tuple/dict/set/bool/None` 仍大量直接充当 runtime value（host 边界与兼容容错处）；
- `eq` 仍由 Python `is` 支撑；
- `cond` / VM truthiness 仍受 Python 假值污染；
- `pre-symbol-space-chain` 已是带 `(membership, resolver)` 的真实 chain
  （lisp → number → char → string → stdlib → head，`SymbolSpace.resolve` 逐层回退），
  但 profile 组合与 fold 计划的显式 API 仍待收口；
- module / fold 的运行时路径已统一到 `qy/import_/from_fold.py::fold_import` 与
  `iter_selected_exports`（选择逻辑单源）；provisional module 已共用该 primitive，
  HIR lowering / macro expand 仍是近似实现；
- compile-time env 仍只是 runtime env facade；
- LIR 仍较薄，未完全承担低层职责；
- register VM 仍承担较多 host-call compatibility；
- legacy operator dispatch（`PureOperator` / `ScopeOperator` / `ControlOperator` / `EffectOperator` / `MetaOperator`）仍是
  `qy.core` 既有算子的实现方式，尚未逐个迁到 MIR/LIR/bytecode/VM；`sem/runtime.py` 只剩 `EffectDefinition`；
- `io`、`truthy`、runtime identity 仍未落地；`reify` 已有最小实现（partial、ScopeOperator、无 effect 路径）。

## 2.3 当前主要事实漂移

1. ~~`qy/frontend/form.py` 的 `Form` 联合包含 tuple / `SpannedTuple` / `DottedTuple`，
   `TupleAtom` 包含 `str | int | float | bool | bytes | None`；兼容 API 暴露 Python tuple。~~
   ✅ 已闭合：`qy/frontend/form.py` 已删除；`Symbol` / `Chain` / `QyNil` / `Form` 与
   `get_span` 的真源是 `qy/core/syntax.py`；`Form = Symbol | Chain | QyNil`；
   `form_to_tuple` / `TupleForm` / `read_tuple` / `write_tuple` / `SpannedTuple` /
   `DottedTuple` 全部删除（含公共导出）；`surface.py` 的 tuple 版实现已删；
   `macro/hygiene.py` 改为 chain 表示并保留 span；
   `qy/import_/operators.py` 的 `_is_special_form` / `_parse_export_names` / `_from_import`
   也已 chain-native（此前 `from` 算子把参数拼成 tuple 传给 chain-only 的
   `parse_from_import`，实际恒抛异常）。
2. ~~quoted literal 已在 reader 阶段变成 Python `str`（`_decode_string_symbol` 经
   `ast.literal_eval` 解出），兼容 API 入口。~~ ✅ 兼容入口已删除；quote 现在一律
   返回 syntax datum（`Symbol` / `Chain` / `nil`），HIR H11 已收紧为只接受
   syntax datum，不再有物化尾巴（见第 7 条）。
3. ~~`qy/sem/core.py` 里的 `ChainValue` 与 `qy/core/syntax.py` 的 syntax `Chain` 并存。~~
   ✅ 已闭合：`qy.sem` 不再定义 datum 或 Qy 自身对象；`NIL` / `NilValue` / `SymbolValue` /
   `ChainValue` / `DatumValue` 删除；`nil` / `T` / `none` 同处 `qy/core/syntax.py`；
   迁移期桥接层 `qy/sem/bridge.py` 已删除。
4. `1` 等 spelling 现在通过 number-ss / string-ss / char-ss 的 `(membership, resolver)`
   参与真实的 chain walk（`SymbolSpace.resolve` 逐层回退）；`literal_resolver` 只是链
   miss 之后的 profile escape hatch，不再是主解析路径；
5. `(define 1 10)` 在当前 space 绑定 `1`，按链顺序 shadow number-ss 的字面量
   （语言允许在符号空间中定义任意符号）；行为已由「`define` = current-space-once +
   chain lookup」解释；
6. `qy.core` 仍混入 profile / compat 能力；
7. 标准数据算子已返回 Qy `TupleValue` / `ListValue` / `DictValue` / `SetValue`；
   `session/pre_ss.try_default_literal` 返回 `IntValue` / `FloatValue` / `StringValue` /
   `CharValue`（不再是宿主 `str` / `int` / `float`）；HIR H11 只接受
   `Symbol | Chain | nil`，宿主标量进入 `QuoteExpr.form` 会报错；剩余是 host 边界
   （扩展注入）按显式 `qy.sem.convert` 转换处理；
8. `eq` 已脱离 Python identity / interning，后续还需补完整结构相等算子；
9. `cond` 已是 nil-only truth；标准 profile 的 `truthy` 负责复杂真值；
10. `truthy` 已有正式 operator，但还需按 profile 层文档继续收口；
11. `io` 仍只是 `print/echo` 模块，不是 Qy runtime model；
12. `reify` 已有最小实现（ScopeOperator、partial-failure、无 effect 路径）；
13. `HostReference` 已由 `(type ...)` 分类为 `host`（不再落成 `any`），`eq`/`is` 按 identity、dict key 命中、`format_value` → `<host>` 已落地（见 §9¾ item 18）；更完整的 runtime identity 容器（跨宿主 adapter）仍待推进；
14. macro compile-time evaluator 已脱离 bytecode / register VM；compile-time namespace 仍需继续显式化为独立 slot/layout；
15. `from` 的运行时 fold 已收口到 `qy/import_/from_fold.py::fold_import`，由运行时算子
    (`qy/import_/operators.py`) 与 register VM (`qy/vm/instance/machine.py`) 共用
    （冲突按 define-once 原子检查）；编译期 provisional module、HIR lowering 的
    `(from ...)` 校验与 scope 记账现也共用 `iter_selected_exports` /
    `missing_export_names`（选择逻辑单源）；只剩 macro expand 因其走 compile-time macro
    namespace 而非 `StandardModule` 仍独立；子模块从 `fold.py` 改名为 `from_fold.py`
    （否则会 shadow `qy.import_.fold` 核心算子函数——已修）；
    （本轮已修：provisional module 现在识别 `(define name value)` 导出，且其 `from` 解析不再把
    chain 转成 tuple——同源单元 `(from ...)` 导入 `define`/再导出绑定此前会误报 no export；）
16. ~~`quasiquote` nested 路径仍依赖过时 `list/append` 假设。~~ ✅ 已闭合：
    quasiquote 展开统一到 `qy/core/quasiquote.py`（macro expand 与 HIR lowering 共用一份实现），
    不再有第二份 tuple 版实现；
17. 默认 LIR 仍以 compat dialect 为主，但主 pipeline 已执行 `mir.validate` / `lir.verify`，bytecode emit 会拒绝非 VM compat opcode；
18. LIR abstract-machine dialect 已闭合：`lower_effects` + `passes/lir/spaces.py` 产出 `frame_layout` / `handlers` / `continuations` / `symbol_spaces`，把 `ENTER_SCOPE`/`DEFINE_ONCE` 降成 `SS_ENTER`/`SS_LEAVE`/`SLOT_COMPLETE`（L5–L12 全部有数据，L11/L12 CFG-aware），HIR 层 `resolve.spaces` 已实现并把 layout 下沉到 MIR/LIR/bytecode，**VM 已执行 abstract-machine opcode**（与 compat 方言在 86 语料上 diffs=0，`tests/test_abstract_machine_vm.py`）；仍缺：continuation `saved_registers` 由保守全集精化为活跃区间，以及 effect frame 从 VM Python 对象上移到 LIR/ABI 模型；
19. effect frame 仍主要由 VM 中的 Python 对象承担；
20. pending-binding / incomplete-value effort 尚未实现；但前置的「define 只提升 binding」已在 pipeline 落地（`(pipeline (define x 1) (+ x 1))`、`(let () (pipeline (define x 1)) x)`、pipeline 内 defun 前后向引用均可解析），运行期读到未完成 slot 目前仍是占位行为，而非 effort；
21. ✅ 已完成：`UserFunction` / `qy/vm/instance/legacy_eval.py` / `ComponentOperator` 已删除，`lambda`/`defun`/module-local defun 统一编译为 `BytecodeFunctionValue`；module-local defun 采用两阶段预置（compile-time `MacroFunction` 占位 + 管线编译的运行期值），宏体在**编译期调用** module-local defun 会得到明确诊断；
22. docs 中仍有少量旧说法需要持续清理（本轮已修 `qy FILE` / typer / 管线顺序 / `effect.analyze` 状态）。

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

## Phase A0. 包结构收口（已完成）

本阶段目标是先保证目录结构和职责边界正确；测试失败可以后续处理，但不能继续让错误结构扩散。
§7 的 15 项推进顺序已全部落地，此阶段不再是最前线。

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

**状态**：本节已 100% 完成。

所有同名 module/package 冲突已全部解决，无残留旧顶层文件：

- `qy/macro/` (含 `expand.py`, `hygiene.py`, `evaluator.py`, `scope.py`, `trace.py`)
- `qy/cli/` (含 `commands/`, `_pipeline.py`, `_common.py`)
- `qy/errors/` (re-export `QyError`, `QySyntaxError`, `EvaluationError`, `QyResolveError`,
  `QyTypeError`, `QyArityError`, `QyCapabilityError`, `QyReifyError`, `QyEffectError`,
  `QyEffectSignal`, `QyRuntimeError`, `QyPythonError`, `QyCancelledError`, `QyTimeoutError`,
  `QyAggregateError`, `SourceSpan`, `TraceFrame`, `format_qy_error`)
- `qy/ir/` (含 `hir/`, `mir/`, `lir/` 子包，节点 / spec / dump / verify 全部就位)
- `qy/diag/` (替代 `qy/diagnostics.py`)
- `qy/frontend/` (替代 `qy/reader.py`)

后续若新增顶层包，请避免重名同步引入同名 `.py`。

历史已迁移顺序（保留供审计）：

- `qy/macro.py` -> `qy/macro/__init__.py` → 旧文件已删除
- `qy/cli.py` -> `qy/cli/__init__.py` + `qy/cli/commands/*` → 旧文件已删除
- `qy/errors.py` -> `qy/errors/__init__.py` → 旧文件已删除
- `qy/ir.py` -> `qy/ir/__init__.py` → 旧文件已删除
- `qy/mir.py` -> `qy/ir/mir/__init__.py` → 旧文件已删除
- `qy/lir.py` -> `qy/ir/lir/__init__.py` → 旧文件已删除
- `qy/ir/hir.py` -> `qy/ir/hir/__init__.py` / `node.py` → 旧文件已删除
- `qy/ir/mir.py` -> `qy/ir/mir/__init__.py` / `node.py` → 旧文件已删除
- `qy/ir/lir.py` -> `qy/ir/lir/__init__.py` / `node.py` → 旧文件已删除

历史已知风险（已全部清空，仅记录于 git log 与 commit history）：

- `qy/macro/` 会遮蔽 `qy/macro.py`；需要保证 package 已暴露 `MacroDefinition` 等 public 类型。
- `qy/errors/` 会遮蔽 `qy/errors.py`；需要保证 package 已暴露全部 public error API。
- `qy/ir/lir/`、`qy/ir/mir/` 会遮蔽同名 `.py` 文件；搬迁完成前 import 可能失败。
- `qy/ir/hir/` 之前没有 `__init__.py`，一旦添加就会遮蔽 `qy/ir/hir.py`，必须同批迁入 public API。
- top-level `qy/lir.py` 之前仍可能遮蔽目标 LIR public API；`qy/__init__.py` 已改为从 `qy.ir.lir` 导入。
- `qy/cli/commands/*` 与 `qy/vm/{debug,emit,stack}.py` 之前的占位 docstring 已替换为中文职责说明。
- `uv run qy --help` 之前可能触发 `qy/types.py` 遮蔽 stdlib `types` 的启动问题；`qy/types.py`
  已删除，console-script 与 `python -m qy` 均工作。

### A0.2.1 删除计划

**状态**：本节内容已 100% 完成。

- 迁移后删除 25 个顶层文件（`qy/macro.py`、`qy/cli.py`、`qy/errors.py`、`qy/diagnostics.py`、
  `qy/reader.py`、`qy/ir.py`、`qy/mir.py`、`qy/lir.py`、`qy/ir/hir.py`、`qy/ir/mir.py`、`qy/ir/lir.py`、
  `qy/lowering.py`、`qy/mir_lowering.py`、`qy/lir_lowering.py`、`qy/bytecode.py`、
  `qy/bytecode_compiler.py`、`qy/register_vm.py`、`qy/virtual_stack.py`、`qy/analyzer.py`、
  `qy/formatter.py`、`qy/lsp.py`、`qy/benchmark.py`、`qy/source_modules.py`、`qy/llvm_codegen.py`、
  `qy/types.py`）：**已全部移除**，对应 package (`qy/macro/`, `qy/cli/`, `qy/errors/`, `qy/frontend/`,
  `qy/ir/`, `qy/analysis/`, `qy/tools/`, `qy/backend/`, `qy/vm/`, ...) 已就位并暴露全部 public API，
  全树 `from qy.<legacy_module> import …` 命中数：**0**。`tests/test_vm_instance_migration.py:31-32`
  作为正守卫持续断言 `qy.register_vm` 不存在。

- 语义替代后删除 14 个顶层文件 + `qy/stdlib/`：
  `qy/evaluator.py`、`qy/eval_runtime.py`、`qy/async_runtime.py`、`qy/symbol_utils.py`、
  `qy/operators.py`、`qy/operator_runtime.py`、`qy/operator_signature.py`、`qy/operator_docs.py`、
  `qy/runtime_values.py`、`qy/environment.py`、`qy/continuation.py`、`qy/values.py`、
  `qy/literals.py`、`qy/semantics.py`、`qy/stdlib/`：**已全部移除**。
  `qy/stdlib/` 仅剩 30 行 shim (`qy/stdlib/__init__.py`) re-export 自 `qy.std/`，
  移除 shim 是用户可见的破坏性变更，未在本会话处理。

- 可直接删除（cache / build artifacts）：
  - `qy/**/__pycache__/`
  - `.pytest_cache/`、`.ruff_cache/`、`.mypy_cache/`、`.ty/`
  - `QyLang.egg-info/`、`dist/`、packaging 临时 `build/`
  - `*.py.original`、`*.py.restored`

  当前状态：2026-08-02 已执行 `git clean -fdx` 清空全部上述 artifact。
  残留 check：`git ls-files --others --exclude-standard` 应返回空。

历史记录保留如下供审计：

<details><summary>删除规则（已完成）</summary>

标记规则：

- 迁移后删除文件使用 `QY_DELETE_AFTER_MIGRATION: target=...`。
- 语义替代后删除文件使用 `QY_DELETE_AFTER_SEMANTIC_REPLACEMENT: target=...`。
- 后续用 `rg QY_DELETE_AFTER qy` 审计待删范围。

迁移后删除清单：见上方 "迁移后删除 25 个顶层文件"。

语义替代后删除清单：见上方 "语义替代后删除 14 个顶层文件 + `qy/stdlib/`"。

</details>

### A0.3 `stdlib` -> `std`

**状态**：目标包名是 `qy/std/`，已就位。
`qy/stdlib/` 当前仅剩 30 行兼容 shim (`qy/stdlib/__init__.py`) re-export 自 `qy.std/`，
不得在 shim 内新增长期实现；移除 shim 是一次性用户可见破坏变更，需独立审批。

- docs 中可以暂时提到 `stdlib` 作为现状，但目标命名必须写作 `std`；
- `docs/stdlib-operators.md` 当前可保留文件名，后续重命名为 `docs/stdlib-operators.md`。

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
- `docs/stdlib-operators.md` 当前只描述可变 std 草案，后续改名为 `docs/stdlib-operators.md`；
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

- 每批工作记录到本文档 §2（已完成 / 仍在过渡 / 事实漂移三类），细节以 git commit message 为准；
  不再维护根目录 `report.md`（违反"设计文档只在 docs/ 且必须注册"的规则）：
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
- ~~`UserFunction` 迁到 bytecode function~~ ✅（已删除 `UserFunction`/`legacy_eval`）；
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

> 已修：`mod` 的 integer 路径用 Python `%`（结果符号跟随除数），float 路径却用 C `fmod`
> （截断余数），对负数不一致；现三宿主统一为 Python `%`（floored），
> `tests/qy/47_number_mod.qy` 覆盖负数 int/float。
> 已补：`number?` 与 `remainder`（截断余数，符号跟随被除数）在 prelude 与 `qy.num`
> 三宿主提供；`tests/qy/55_std_primitives.qy` 覆盖。

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

> 维护提示：`benchmarks/baseline.json` 生成于 2026-05，**早于** MIR 优化默认开启
> （`7b18c98`，2026-09），因此 `make bench-check` 现在会把「基线漂移」报成大量回退
> （连 `source` 相位都慢数倍，属环境/基线差异）。重新 `make bench-baseline` 之前，
> 不应把它当作有效回归门禁。

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

**当前实际状态（已修复）**：`qy llvm` 输出合法 LLVM IR，`llc` → `clang`(+`qy/resources/libqy`) 可生成原生可执行文件，且 `00/02/03/09` validation 样例结果与 register VM 一致（`make llvm-verify` PASS）。本轮修复的关键问题：

- `%qy_value` 布局改为与 `qy.h` 一致（`{ i8, [7 x i8], [3 x i64] }`）；
- 采用 C ABI：32-byte 结构体以 `ptr sret(%qy_value) align 8` 返回、`ptr byval(%qy_value) align 8` 传参，并使用 opaque pointer（`ptr`）——早期按值传递导致运行时读到 tag 0；
- 寄存器改为 entry block 的 `alloca`，def/use 走内存，去掉未定义的 `%reg_N` 与 SSA 名重复；
- 去掉非法 `!llvm.index`、jump-target 自跳转；`%call.argv` 改用 GEP 索引；
- 补全模块契约 `@qy_fn_table` / `@qy_fn_table_size` / `@qy_main` / `@main`。
- Makefile：`llvm` 默认输出与 `llvm-verify` 对齐（原一个写 `a.out`、一个跑基线名）。

详见 `docs/llvm-backend.md`。当前支持 int/nil/T/string、内建算术、无自由变量的函数、let/cond/pipeline；effect/module/macro/并行仍降为 nil 占位。

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
   - ~~`UserFunction` -> bytecode function~~ ✅ 已完成；
   - evaluator 退场；
   - compat stdlib 下沉。
6. **自举解释器推进**
   - 保持 `meta-interp/cases/` 与受支持 `tests/qy` 用例的对拍；
   - 逐步补齐 py 宿主互操作、number family 的 concrete 类型语义；
   - 性能：消除解释器全局 lookup 的线性扫描，再谈阶段 3 自解释。

---

# 9⅞. 本轮多宿主收尾（Go 宿主 / 自举验证）

- **Go 宿主对等补齐**：整数改 `math/big.Int` 任意精度（JSON `UseNumber()` 精确解析；
  二元除法异号复刻 Python 的 `int(a/b)` float 路径；定宽越界 `numeric-overflow`），
  并支持 abstract-machine 方言（`symbol_spaces` layout + `SLOT_COMPLETE`；顺带修掉
  AM 的 `HANDLE` specs 是裸 tuple 导致 6 个 effect 语料 unhandled 的真实缺口）。
  两方言均 **56/56**、`bigint_conformance.sh` **13/13**（两方言）。
- **大整数正式语料**：新增 `tests/qy/53_number_bigint.qy`（2^53 加减乘、30!、负数、
  比较、取模），在 **Python / TypeScript / Go 三宿主 × 两种方言**下输出一致，
  并接入 qytest、TS/Go conformance、`tests/test_bytecode_json.py` 与自举对拍清单。


- **TypeScript 宿主补齐**：整数改 `bigint` + 自写精确 JSON 解析器（2^53 之后不再丢精度，
  语义逐条对齐 `number_ops.py`，含二元除法的 float 路径）；`qy export --dialect
  {compat,abstract-machine}`，两种方言均 **54/54**；`parallel`/`all`/`race` 在保守纯度
  判定下真并发（effect/IO/共享状态回退顺序）；`RUNTIME_EVAL` 支持子集写入注释。
- **交换格式完备性**：`serialize_bytecode_json` 曾把 abstract-machine 的
  `LIRBindingAddr` 写成 `{"type":"unknown"}`（连 Python 自己的 loader 都拒绝，该方言
  产物无法离开 Python）。现新增 `binding_addr` 操作数与顶层 `symbol_spaces`（layout），
  并把 layout 挂到每个 `BytecodeFunction`（VM 的 `_slot_symbol` 读函数级 layout）；
  Python/TS 两种方言往返均 **54/54**。


- **Go 宿主完成**：新增根 `go.mod`（module `github.com/Cosmic-Developers-Union/Qy`，
  零第三方依赖，`qy/backend/golang` 与 `go-reader` 同属一个 module）；按已验证 54/54 的
  TS 宿主同构重写 Go VM（`pkg/vm`、`pkg/bytecode`、`pkg/stdlib`），补 `CALL_BUILTIN`、
  `hygiene_bindings`（惰性别名）、`module_macro_exports`（编译期宏导出跳过绑定）、
  字面量回退解析与逐字节对齐的 `display`；`go build/vet/test ./...` 全通过，
  `bash qy/backend/golang/conformance.sh` → **54/54**；`examples/go/` 三个示例可跑。
  限制见 `docs/hosts.md` §5。
- **自举验证接入**：`make test-selfhost`（`compare.sh` 19/19 + `QY_META_SELF=1`
  解释器解释自身）并纳入 `make ci`；修正 `todo.md` 中"宏 hygiene 未实现"的过时说法
  （`meta-interp/main.qy` 已实现 binder 重命名 / definition-site free symbol /
  `capture` / `gensym`）。
- **`.gitignore` 陷阱修复**：`*.mod*`（内核模块产物）会连带匹配 `go.mod`，导致 Go module
  文件被静默忽略、无法提交；改为显式 `!/go.mod`、`!/go.sum`，并新增守卫测试
  `tests/test_target_architecture_guards.py::test_repo_root_toolchain_files_are_not_git_ignored`。

# 9¾. 多宿主计划（新一轮目标）

目标：让 Qy 能作为**嵌入式语言**在 Python / TypeScript(JS) / Go 三种宿主中工作。
三种宿主的基础都是「能执行 Qy 字节码的虚拟机」，外加宿主语言扩展（用宿主语言写算子、
传宿主对象、按 capability 授权），并要求 Qy 自举（解释器能解释自身）。

宿主 / 后端矩阵（现状）：

| 宿主 | 解释执行（VM 跑字节码） | 编译后端 | 宿主语言扩展 |
| --- | --- | --- | --- |
| Python | ✅ `RegisterVirtualMachine` + `Qy.run_bytecode_json` / `qy run --bytecode` | ✅ Python VM 字节码 / LLVM / WASM | ✅ `qy/ext`（descriptor + registry + capability） |
| TypeScript / JS | ✅ `qy/backend/typescript/`（bun + TS，`qyvm` CLI + `src/embed.ts`） | 复用 Python 侧产出的字节码 JSON；WASM 由 Python 侧产出 | ✅ `registerHostFunction`（`src/embed.ts`） |
| Go | ✅ `qy/backend/golang/`（根 `go.mod`，`go build/vet/test` + conformance 接入 `make test-go`/CI） | 复用字节码 JSON | ✅ `examples/go/qyhost`（宿主算子注册/覆盖） |

**交换格式（三种宿主共享的契约）**：`qy export FILE -o prog.json` 输出的 JSON 字节码。
它必须 (1) 可表示（每个常量都能编码，不得退化成 `{"type":"unknown"}`）、(2) 可还原
（装载后执行结果与直接执行一致）。

## 已完成

- **交换格式补对端**：Python 侧原先只能导出、不能装载。新增
  `qy/backend/vm/bytecode.py::load_bytecode_json`（`serialize_bytecode_json` 的对端），
  值与 `qy.sem.core` 的值类型按 `{type, class, value}` 通用编解码；`nil` / `T` /
  `none` 保持单例；遇到无法编码的值**显式报错**而不是退化成 repr 字符串（此前
  `IntValue` 等会被编码成 `{"type":"unknown","value":"IntValue(value=2)"}`，装载后
  变成字符串，运行期报 `+ expects a number, got str`）。
- **宿主入口**：`Qy.run_bytecode_json` / `AsyncQy.run_bytecode_json`（嵌入 API）与
  `qy run --bytecode FILE`（含 `-` 读 stdin）。
- **一致性测试**：`tests/test_bytecode_json.py` —— `tests/qy` 全部 56 个程序
  「编译 → 导出 → 装载 → 执行」结果一致，导出中无 `unknown` 常量；另覆盖单例往返、
  非法版本/无法编码值的报错、CLI 与嵌入 API。
- **自举基线**：`QY_META_SELF=1 pytest tests/test_meta_interp.py` 通过（解释器源码
  被自身解释后仍能得到正确结果）；默认 skip 仅因耗时。

## 本轮闭合

1. ✅ **TypeScript 宿主**：`qy/backend/typescript/`（bun + TS）已实现装载 / 值模型 / 帧 /
   指令（含 `CALL_BUILTIN`）/ 标准库 / 嵌入 API（`src/embed.ts`）/ `qyvm` CLI；
   `bun test` 49 pass，两方言 conformance 各 **56/56**，bigint **13/13**。
2. ⏳ **Python 宿主补齐**：宿主扩展（capability / descriptor）已文档化
   （`docs/extensions.md`）并有 `tests/test_extensions.py` 守卫；LLVM 后端已知限制
   （`Chain` 等常量、未解析符号的 IR 生成）仍待补齐，归入「后端覆盖」工作项
   （见 `docs/llvm-backend.md` §限制）。
3. ✅ **Go 宿主**：根 `go.mod`（零第三方依赖）、Go 单测、`make test-go`/CI，
   `qy export` → `qyvm` 打通，`CALL_BUILTIN` 已补；两方言 **76/76**，bigint **13/13**。
4. ✅ **自举推进**：`make test-selfhost` 已纳入 `make ci`；宏 hygiene（`gensym` / `capture`）
   已在 `meta-interp/main.qy` 实现。
5. ✅ **跨宿主一致性**：`tests/test_bytecode_json.py`（Python 往返，全新环境执行）+
   TS/Go 各自 conformance，构成「同一 .qy → 三宿主 → 输出一致」的差分门禁。
6. ✅ **跨宿主修复（本轮）**：
   - improper chain（dotted pair）的交换格式：三侧 loader 都误把任意 dict 当链节点，
     导致 tail 解成 `Chain(None, nil)`；按「有 `head` 才是节点」统一修复
     （Python / TS / Go），并加三宿主回归测试；
   - 卫生宏别名解析范围：TS/Go 把别名目标在**当前 env** 解析，调用点 shadow 会污染
     定义点自由符号（`(let ((+ ...)) (add-one 41))` 得 0 而非 42）；改为与 Python
     `_install_hygiene_aliases` 一致，从**程序根 env** 解析；
   - 新增 `tests/qy/54_hygiene_shadow.qy` 作为三宿主共享回归语料（corpus 55 → 56）。
7. ✅ **跨宿主标准库补齐（本轮）**：TS/Go 之前缺 `string->number`（既不在 prelude，
   也不在 `qy.num`）与整个 `qy.char` 模块，任何 `(string->number ...)` /
   `(from qy.char import ...)` 程序在 TS/Go 上都会失败；现补齐（`string->number`、
   `qy.char` 15 个算子）并加共享语料 `tests/qy/55_std_primitives.qy`（corpus 56 → 57）。
8. ✅ **conformance 语料扩展（本轮）**：TS/Go conformance 之前只跑 `tests/qy`，导致
   `meta-interp/cases` 里的 hygiene / dotted-pair 等缺陷长期不在门禁内；现两个脚本
   同时跑 `tests/qy`（57）+ `meta-interp/cases`（19），各 **76/76**（两种方言）。
9. ✅ **fold primitive 收口 + 命名冲突修复（本轮）**：`qy/import_/fold.py` 新增
   `iter_selected_exports`，运行时 `from`（算子 / register VM）与编译期 provisional
   module 共用同一「选择逻辑」（runtime 导出 / 宏导出 / 缺失 require 语义）；子模块
   改名为 `qy/import_/from_fold.py`——否则会 shadow `qy.import_.fold` 核心算子函数
   （`from qy.import_ import fold` 会拿到 module 而不是算子）。
10. ✅ **formatter 顶层 reader macro 拆分修复（本轮）**：CST 把顶层的 `'` / `` ` `` 前缀
    与其操作数拆成相邻子节点，`_collect_lines` 之前按子节点逐个成 form，导致 `'(a b)`
    被格式化成 `'` 与 `(a b)` 两个顶层 form（语义改变，`18_dotted_pairs.qy` 会报
    unresolved symbol）；现按「前缀 + 紧邻操作数」重新分组，并新增 formatter 全语料幂等
    + 格式化前后 `qy run` 输出一致的参数化护栏（`tests/test_formatter.py`）。
11. ✅ **`eq` 对 char 按值比较（本轮）**：`_eq`（Python）/ `eq`（TS）/ `Eq`（Go）都漏了
    `CharValue` 分支，`(eq #\a #\a)` 在三宿主都返回 nil（与「原子按值比较」矛盾，也影响
    char 作为 dict key）；现统一按 `value` 比较，并加语料与单测。
12. ✅ **`(type <char>)` 分类修复（本轮）**：`qy.sem.classify.literal_type` 漏了
    `CharValue` 分支，`(type #\a)` 在 Python 返回 `any`，而 TS/Go 返回 `char`（跨宿主
    不一致）；现统一为 `char`，并加单测与语料。
13. ✅ **`(type <operator/function/effect>)` 分类修复（本轮）**：TS/Go 的 `type` 对
    算子/函数/effect 值落到兜底 `object`，Python 返回 `operator`/`function`/`effect`；
    现 TS 按 `PureOperatorValue`/`RawOperatorValue`/`EffectDefinition`/
    `BytecodeFunctionValue`、Go 按 `*vm.PureOperator`/`*vm.RawOperator`/
    `*vm.EffectDefinition`/`*vm.FunctionValue` 补齐，三宿主一致。
    （本轮另用「算子 × 值种类」矩阵对拍：data 126、string/char 158、number 1344、
    container 156、reify 13 组合，除已修项外 0 mismatch。）
14. ✅ **TS/Go 具体数值空间 `qy.int8`..`qy.float128`（本轮）**：Python 注册的 12 个
    具体数值模块 TS/Go 之前完全缺失（`(from qy.int8 import ...)` 报缺模块）。现新增
    `qy/backend/typescript/src/stdlib/number_spaces.ts` 与 Go `number_spaces.go`：构造器 +
    谓词 + 类型化算术（floored `/`、`mod`/`rem` 同为 floored）+ 位运算 + `min-value` /
    `max-value` / `bits`（直接值绑定），并在各自 registry 注册；`tests/qy/55_std_primitives.qy`
    增加 int8 覆盖。残留模块面差异只剩 `qy.legacy`（已废弃 spawn/await，故意不补）。
15. ✅ **`component` 编译期宏不再泄漏到运行期（本轮）**：`(define name (component ...))`
    在 `macro/expand.py` 只注册宏，却仍保留运行期 `define`，导致 `component` 出现在导出
    bytecode 里（不实现宏运行期的 TS/Go 报 `unresolved symbol 'component'`，标准参考
    `examples/qy/hello.qy` 都跑不起来）。现注册成功后返回 `nil`（调用方过滤），
    `hello.qy` 导出中 `component` 出现 0 次；`tests/test_component.py` 加护栏。
16. ✅ **TS/Go 实现 `this`/`slot`/`bind`（本轮）**：`qy.core` 的 symbol-space 显式建模
    算子 TS/Go 之前完全缺失（`hello.qy` 接着报 `unresolved symbol 'this'`）。现 TS/Go 用
    raw operator 实现 `this`（返回当前 env）、`slot`（单例哨兵）、`bind`（按 Python 语义
    写入当前 symbol-space，slot 仅占位），并在 prelude 与 `qy.core` 注册。
    `examples/qy/hello.qy` 现可在 TS/Go 完整执行，仅 `(this)` / `(slot)` 的 host 对象
    repr 行无法逐字节对齐（与 `todo.md` §9½ 记录的 meta-interp 近似一致），故仍不纳入
    逐字节自动对拍；新增 `tests/test_examples_ts.py::test_typescript_accepts_hello_golden_file`
    做「行数与 Python 一致」的烟测。
17. ✅ **Qy artifact 的稳定文本表示（本轮）**：算子 / effect / module / symbol-space /
    slot 这些 artifact 之前 Python 走 `repr`（泄漏 `PureOperator(name=..., func=<... 0x...>)`
    与内存地址），而 TS/Go 已是 `<operator x>` / `<symbol-space>` / `<slot>`。现 Python
    `format_value` 统一为同一套表示（`__qy_format__` hook + 显式分支），三宿主对
    `+` / `(this)` / `(slot)` / `examples/qy/hello.qy` 输出**逐字节一致**；
    `tests/test_examples_ts.py` 的 TS/Go golden 测试改为断言逐字节相等。
18. ✅ **host reference 的 identity 语义与稳定显示（本轮）**：`_eq` 之前没有
    `HostReference` 分支，`(eq host host)`（同一包装对象）返回 nil，host reference 作为
    dict key 也永不命中；`format_value` 还泄漏 `HostReference(value=<object ...>)`。
    现 `_eq` 按 identity 比较（同一包装对象为 T，与 dataclass `eq=False` 一致），
    `format_value` 输出 `<host>`；`tests/test_basic_operators.py` 加护栏。
19. ✅ **CLI 调试/后端命令的 error 短路（本轮）**：`qy/cli/_common.py::compile_source_to`
    之前用默认 `PipelineOptions(error_threshold=10**6)`，于是一个未解析符号会继续
    lowering 到 LIR，产生误导性的二次内部错误 "LIR main function index 0 is out of
    range for 0 LIR functions"。现 CLI 调试命令用 `error_threshold=1`（同一 pass 内仍会
    收集全部诊断），`hir`/`mir`/`lir`/`bytecode`/`wasm`/`llvm` 只报真实诊断；
    `qy check` / LSP 仍走默认阈值收集全部诊断。`tests/test_cli_commands.py` 加护栏。
20. ✅ **`qy.io` 的 `display`/`newline` 与 TS/Go head 层（本轮）**：TS/Go 早已在
    `qy.io` 绑定 `display`/`newline`，Python 却没有（跨宿主模块面缺口），且 TS/Go 的
    `display` 误等价于 `print`（换行），与后端 `display` 内建（不换行）不一致。现
    Python 补 `display`（不换行）/`newline`，TS/Go 的 `display` 改为不换行；并给 TS/Go
    prelude 增加顶层可写 **head** 层（对应 Python `pre-ssc-head`），使
    `(from qy.io import ...)` 不再与 `qy.io` 空间自身冲突。`hello.qy` 仍逐字节一致。
21. ✅ **compat handler 裸返回 continuation 的死循环（本轮）**：compat VM 的
    `_dispatch_effect` 把 handler 返回的 `QyContinuation` 当成「再次 dispatch」信号，
    于是 `(handle (perform ask 1) ((ask (arg k) k)))` 无限循环（TS/Go 同样）；而
    abstract-machine 方言与 AM 路径是直接返回。现三宿主 compat 路径改为直接返回
    handler 结果（continuation 只是普通 runtime value），并给 Python `format_value`
    补 `<continuation>` 表示；`tests/test_register_vm_semantics.py` 加回归。
22. ✅ **深非尾递归不得泄漏 Python `RecursionError`（本轮）**：Python 调用栈有限，
    非尾递归深度约 500 就会抛 `RecursionError` 并在 CLI 打出完整 Python traceback；
    TS/Go 用显式帧栈可到更深（1e6 尾递归、1e4 非尾都通过）。现 Python VM 的顶层
    `evaluate_program` 捕获 `RecursionError` 并转为语言级 `QyRuntimeError`
    （`maximum recursion depth exceeded`，无 traceback）；深度差异记入 `docs/hosts.md` §5。
23. ✅ **`qy export` 的错误级联 + `docs/op.md` 的 eq 描述（本轮）**：`qy export` 之前用
    `error_threshold=10**6`，未解析符号会继续 lowering 出 "LIR main function index ...
    out of range" 二次内部错误（与 item 19 的 CLI 调试命令同类）；现改为
    `error_threshold=1`（同一 pass 内仍收集全部诊断），cascade 测试纳入 `export`。另修正
    `docs/op.md` 的 `eq` 描述（原子按值、引用类型按 identity），与实现一致。
24. ✅ **`race` 确定性 + 文档漂移（本轮）**：Python `RACE_FIRST` 用 `next(iter(done))`
    在纯同步 thunk 下取集合里任意一个（实测取到第二个），而 TS `Promise.race` / Go 首个
    thunk 都取第一个；现 Python 改为 `min(done, key=tasks.index)`，三宿主一致返回最先
    声明的。`tests/qy/28_race_first.qy` 扩展覆盖，`docs/hosts.md` §5 更新。另修正
    `docs/stdlib-operators.md` 的 `eq` 原则与 IO 表（补 `display`/`newline`）。
25. ✅ **`CharValue` 的 display 表示（本轮）**：`format_value`/`formatValue`/`FormatValue`
    都让 char 落到 host repr `CharValue(value='a')`（TS/Go 明确复刻 Python 的遗漏）。现
    三宿主统一为 **原文本** `a`（display 语义，与 string 一致；`write`/`reify` 仍用 `#\a`），
    消除最后一处值 repr 泄漏；`tests/test_display.py` 与 `tests/qy/55_std_primitives.qy`
    加覆盖。
26. ✅ **文档漂移：abstract-machine 已接通（本轮）**：`qy/backend/vm/compiler.py` 的
    模块 docstring 仍写「仅接受 compat dialect」，但代码早已接受 `abstract-machine`；
    `docs/lir-effect-frame-design.md` 的「bytecode compiler 尚未处理 abstract machine
    ops / VM 尚未消费」也已过时。现更正：AM 指令已是 VM 可编码/可执行 opcode，剩余
    工作是 layout 字段上移与 compat→AM 默认切换；race 取消行为说明同步。
27. ✅ **VM 性能：虚拟栈 `replace_top` 移出热路径（本轮）**：`_run_function` 之前
    **每条指令**都 `stack.replace_top(_function_stack_frame(...))`（一次自举约 1160 万次），
    纯为保持 trace 顶帧；现只在 `TAIL_CALL` 切换 `frame` 时更新。自举「解释器解释自身」
    从 **~30.6s 降到 ~21.3s（-30%）**；VM/语义/abstract-machine 差分测试全过。
28. ✅ **VM 性能：`SymbolSpace.resolve` 迭代化（本轮）**：把「递归 `_resolve`」的链查找
    改为单次迭代循环、逐层调用 `lookup`（保留唯一 lookup 实现，别名循环语义严格不变，
    `_resolve` 删除）。实测自举仍在 ~21.2–21.9s（与递归版持平：瓶颈是 dict 命中而非调用
    开销），但去掉递归，为超长链与后续缓存优化留出空间；相关测试 + 全量 pytest 通过。
29. ✅ **`Symbol.__hash__`/`__eq__` 显式化（本轮）**：`Symbol` 原为 `@dataclass(frozen,
    slots)`，`span` 用 `compare=False` 排除；现改为 `eq=False` + 手写 `__eq__`（按 name）
    与 `__hash__`（`hash(name)`，str 哈希已缓存），避免每次哈希构造 tuple。语义等价
    （span 不参与相等/哈希），相关测试 + 全量对拍通过。注：本机 load ~10.5/16，自举
    计时噪声大，不以绝对秒数断言收益。
30. ✅ **类型化数值空间的 `/` / `rem` 语义修正（本轮）**：`qy.int8`..`qy.float128`
    的整数 `/` 误用 Python `//`（floored），`rem` 误与 `mod` 同为 floored（`_rem` 的
    docstring 却写 "truncating"）；与 `qy.num`（`/` 截断、`mod` floored、`remainder`
    截断）不一致。现三宿主统一：整数 `/` 向零截断、`rem` 截断、`mod` floored——
    `(/ (int8 -7) (int8 3)) (mod ...) (rem ...)` = `(-2 2 -1)`。补 `tests/test_numeric_spaces.py`
    与 `tests/qy/55_std_primitives.qy` 覆盖，并在 `docs/stdlib-operators.md` 补类型化数值空间章节。
31. ✅ **TS 字符串算子的 code point 语义（本轮）**：TS 的 `string-slice`/`string-at` 用
    UTF-16 `text.length`/`text[i]`，遇到 astral 字符（如 😀）会拆开 surrogate；
    `string-find` 返回 UTF-16 索引（Python/Go 为 code point 索引）；`string-replace`
    用 `split/join`，空 pattern 少首尾（`"abc"` → `a-b-c`，Python/Go 为 `-a-b-c-`）。
    现 TS 统一按 code point（`[...text]`）切片/取字符/换算索引，空 pattern 按 Python
    `str.replace` 语义插入首尾；新增 `test/strings.test.ts` 与语料 unicode 用例。
32. ✅ **Go `string-split`/`string-slice` 缺省参数 + 跨宿主错误码（本轮）**：Go `argAt`
    对缺参返回宿主 nil，而 `optionalString` 只识别 `QyNil`，于是 `(string-split "a b")`、
    `(string-slice "abc" 1)` 直接报类型错误；现 `optionalString` 同时把宿主 nil 视为未提供。
    另：TS/Go `string-split` 空 separator 与 Python 的 `empty separator` 对齐；TS/Go CLI
    错误前缀改为与 Python `qy/errors` 一致的 `QY_*` 码（`QY_TYPE_ERROR`/`QY_RUNTIME_ERROR`
    /`QY_EVALUATION_ERROR`），`car`/`cdr` 错误消息统一用 Qy display 渲染值（消除 TS
    `[object Object]` 泄漏、Go 缺值）。Go full case mapping 差异记入 `docs/hosts.md`。
33. ✅ **随机程序对拍 + 诊断消息归一（本轮）**：新增 `build/fuzz_programs.py`（120 个随机
    Qy 程序 × 3 宿主，比较 stdout + stderr 首行）驱动收口——从 12 处 mismatch 降到 **0**：
    Python `_get` 缺参不再泄漏宿主 `TypeError`（改 `QyArityError`）；`get`/`has?` 在 TS/Go
    先校验 arity；`get`/`len`/`car`/`cdr` 类型错误统一用 Qy display 渲染值；三宿主
    `typeName` 统一返回 Qy 类型标签（char/string/symbol/chain/…，修 Go 缺 `CharValue`→object）；
    TS `QyEffectSignal` 消息与 CLI 映射为 `QY_UNHANDLED_EFFECT: unhandled effect 'x'`；
    Go `string-at` 补 index/length。补 `test/data.test.ts` 与 Python/TS 断言。
34. ✅ **language-form 随机对拍 + Go 容器类型标签（本轮）**：新增 `build/fuzz_forms.py`
    （100 个 `let`/`cond`/`if`/`pipeline`/`lambda` 组合程序）；发现 Go `typeNameOf` 对
    tuple/list/dict/set 返回 `any`（Python/TS 为 `list` 等），已补全；两个 fuzz 现均 **bad 0**。
    扩展 effect 矩阵（25 例）只余 1 处已记录差异：`(parallel (perform e …) …)` Python 并发
    分支内 effect 逃逸为 `QY_AGGREGATE_ERROR`，TS/Go 因保守纯度回退顺序执行并由外层 handler
    处理——已在 `docs/hosts.md` 明确写出。补 `stdlib/diagnostics_test.go`。
35. ✅ **`parallel`/`all`/`race` 的 effect 与错误聚合跨宿主对齐（本轮）**：
    - Python `_parallel_gather`/`_race_first` 采用与 TS 相同的「并发安全判定」
      （`_thunks_are_concurrency_safe`：纯 opcode 白名单 + IO builtin/副作用 symbol），
      分支含 effect/IO 时顺序回退，effect 由外层 handler 处理；
    - `parallel` 的非 effect 错误统一聚合为 `QyAggregateError`：TS 顺序回退也聚合、
      Go `PARALLEL_GATHER` 新增 `vm.AggregateError` 聚合（effect 信号原样上抛），
      两宿主 CLI 映射 `QY_AGGREGATE_ERROR`；`all` 仍抛首个错误。
    - 5 个 probe（effect / eval-error / car-error / all-error / pure）三宿主逐字节一致；
      更新 `docs/hosts.md`、`docs/lir-effect-frame-design.md`。
36. ✅ **宏在 module body 内首次使用时的卫生别名（本轮）**：`(macro m (x) (quasiquote
    (tuple (unquote x))))` 只在 module body 内调用时，`_definition_site_alias` 把卫生别名
    hidden 绑进 module body 的临时子 env，HIR lowering（用顶层 env 做 fallback resolve）看
    不到，报 `unresolved symbol '__qy_hygiene_def_tuple_1'`（若先在顶层用过同一宏则正常）。
    现 `RuntimeSpace.define_hidden_root` 把卫生别名装到 chain 根部，任意子 env 都能解析；
    新增 `tests/test_macroexpand.py` 回归，macro/module/hygiene 矩阵 25 例 0 mismatch。
37. ✅ **闭包/高阶函数对拍 + 函数 arity 错误码统一（本轮）**：新增 `build/matrix_closures.py`
    （26 例：闭包捕获、返回 lambda、递归/互递归、apply、compose、higher-order）。发现
    lambda/defun 参数数量不匹配时 Python/TS 抛 `QY_RUNTIME_ERROR`、Go 抛 `QY_ARITY_ERROR`；
    现统一为 `QyArityError`（`QY_ARITY_ERROR`）。矩阵 26 例 0 mismatch。
38. ✅ **宏参数 `&rest` 支持（本轮）**：编译器宏参数解析只识别 `&body`，而 self-host
    `meta-interp/main.qy` 的宏展开同时识别 `&body` 与 `&rest`——于是 `(macro m (&rest r) …)`
    把 `&rest` 当普通参数、调用报 arity。现 `qy/macro/expand.py` 把 `&rest` 与 `&body` 等价处理
    （都绑定剩余参数为 chain），与 self-host 一致；新增 `tests/test_macroexpand.py` 回归，
    macro/module/hygiene 矩阵仍 0 mismatch。注：`lambda`/`defun` 的 `&rest` 变参语法仍未支持
    （那是需要跨 MIR/LIR/bytecode/host 的特性，另议）。
39. ✅ **reify/eval 对拍 + 类型标签与错误泄漏（本轮）**：新增 `build/matrix_reify2.py`
    （50 例）。修复：①`reify` 失败消息改用 Qy 类型标签（Python 原泄漏 `BytecodeFunctionValue`
    /`PureOperator`/`SetValue`，TS 的 function/operator 返回 `object`，Go 返回 `any`），现三宿主
    一致（`function`/`operator`/`set`/`tuple`…）；②`eval` 内层编译失败不再泄漏宿主 `TypeError`
    （Python traceback），改为语言级错误，未绑定符号报 `QY_UNBOUND_SYMBOL`（与 TS/Go 一致）；
    ③TS `bytecode call resolved to non-callable [object Object]` 改为 Qy display 的 `1`。
    50 例剩 2 例为已记录差异：`eval '(1 2)` Python 编译期拒绝、TS/Go 运行期拒绝（错误码不同）。
40. ✅ **变参函数参数 `&rest` / `&body`（本轮）**：`lambda`/`defun` 参数列表现支持
    `&rest` / `&body <name>`，把剩余实参绑定为 chain（与宏 rest 参数同义）。跨全栈实现：
    HIR `LambdaExpr.rest_param`/`DefunExpr.rest_param` → MIR `MIRFunction.rest_param` →
    LIR `LIRFunction.rest_param` → bytecode `BytecodeFunction.rest_param` + JSON `rest` →
    三宿主 VM `_make_frame`/`makeFrame`/`makeFrame`（定长 arity 检查退化为 `at least N`）。
    新增语料 `tests/qy/56_variadic.qy`（conformance 76→**77**）；三宿主对拍 12 例 0 mismatch。
    `docs/op.md` 记录语法；`docs/hosts.md`/`AGENTS.md` 计数更新。
41. ✅ **变参函数的后端显式诊断（本轮）**：LLVM / wasm emitter 之前只用 `function.params`、
    忽略 `rest_param`，变参函数会被静默当作定长编译（错误代码）。现两后端在 function emitter
    入口检测 `rest_param`，抛 `LLVMUnsupportedError` / `WasmUnsupportedError`（「variadic function」），
    `qy llvm` / `qy wasm` 干净报错；补 `tests/test_llvm_backend.py` / `tests/test_wasm_backend.py`，
    更新 `docs/llvm-backend.md` / `docs/wasm-backend.md`。另跑通变参函数与 tail-call / effect /
    cache / pipeline / parallel / 嵌套函数组合（10 例 0 mismatch）。
42. ✅ **不可恢复 effect 的 resume 强制 + effect 载荷边界（本轮）**：新增
    `build/matrix_numeric_effects.py`，发现 ① 对不可恢复 effect（`mod` 的 divide-by-zero、
    `numeric-overflow`）调用 `resume`：Python 报 `QY_EFFECT_ERROR: ... is not resumable`，
    TS/Go 却静默成功——现 TS `Continuation.resume` / Go `vm.resume` 补上 `resumable` 检查
    （新增 `QyEffectError`/`EffectError` 与 CLI 映射）；② effect 载荷是宿主 dict（Python/TS）
    或 `DictValue`（Go），`(get v 'operation)` 三宿主不一致——现统一为 Qy `DictValue`
    （symbol 键 + Qy 值）：Python `number_ops.effect_payload` + `numeric_spaces` 显式转换、
    TS `performEffect` 集中转换、Go 本就 `NewDict`；divide-by-zero 载荷统一带 `operator`。
    载荷矩阵（`(get v 'operation)`/`(type v)`/`(get v 'result)`）三宿主一致。
54. ✅ **控制/缓存对拍 + Qy library 机制探索（本轮）**：`assert`/`cache` 矩阵 16 例 0 mismatch；
    高阶容器算子（`map`/`filter`/`fold`/`reduce`/`sort`/…）当前均未实现（草案未列）。
    尝试把 draft 的「Qy library」派生数值算子（`inc`/`dec`/`abs`/`zero?`/…）实现为编译期宏
    （`qy/std/library.py` + 注册进 macro namespace）：展开正确，但宏在符号解析前展开，会**遮蔽**
    同名 lexical/`defun` 绑定（`(let ((inc …)) (inc 41))`、`(defun abs …)` 命中的是宏），
    与 Qy 单命名空间语义冲突，已回退；结论写入 `docs/stdlib-operators.md`（Qy library 表格
    增「现状」列 + 遮蔽约束说明）。LLVM 链常量尝试也因 libqy 无 symbol tag 回退（记于本项）。
55. ✅ **宏展开尊重 lexical 遮蔽 + Qy library 落地（本轮）**：宏在符号解析前展开，会遮蔽同名
    lexical/`defun` 绑定。现 `MacroExpansionContext` 增 `shadowed_macros`，宏展开前先查遮蔽：
    `let` 绑定名（值仍在 outer scope 展开，且绑定名不再被误当宏调用——新增 `_macroexpand_let_form`）、
    `lambda`/`defun` 参数、同层后续 `defun`/`define`/`module`/`defeffect` 的名字、顶层后续定义；
    `(define name (component ...))` 是编译期宏注册、不遮蔽。据此把 Qy library 派生算子
    （`inc`/`dec`/`abs`/`zero?`/`positive?`/`negative?`/`even?`/`odd?`/`min`/`max`）以编译期宏
    落地（`qy/std/library.py`）：`(inc 41)`→42，而 `(let ((inc …)) (inc 1))`/`(defun abs …)`
    命中本地绑定。新增语料 `tests/qy/57_library_ops.qy`（conformance 77→**78**）+ 回归测试；
    `docs/stdlib-operators.md` Qy library 表更新为「已实现」。
56. ✅ **交叉对拍全量复跑 + Qy library 文档收口（本轮）**：复跑 8 组跨宿主矩阵——
    `fuzz_programs` 120、`fuzz_forms` 100、`effects2` 25、`macros2` 25、`closures` 26、
    `variadic` 12、`numeric_effects` 12 全部 **bad 0**；`reify2` 50 例只剩 2 处已记录的
    `eval '(1 2)` 编译期/运行期差异。round 46–55 的改动无回归。`docs/stdlib-operators.md`
    的字符串 Qy library 表增「现状」（当前 host operator）；`qy/std/library.py` 记明宏实现的
    限制（派生算子不是一等值，不能 apply；一等派生函数需运行时 Qy library）。
57. ✅ **`ChainFrame.has_membership`：pre-ssc 快照标注动态字面量空间（本轮）**：
    `ChainFrame` 之前只快照固定 `bindings`，`char-ss`/`string-ss`（0 固定绑定、靠
    `(membership, resolver)` 识别字面量）在快照里看起来是空节点。现新增
    `has_membership` 字段并在 `chain().frames()` 填充；`Qy().pre_symbol_space_chain`
    现在能显示 `number-ss`/`char-ss`/`string-ss` 为动态空间（`lisp-ss`/`stdlib`/head 为 False）。
    补 `tests/test_pre_ss.py` 回归与 `docs/language-core-audit.md` B3 说明。
58. ✅ **wasm 后端 float 支持 + `display`/`echo` 返回值修复（本轮）**：新增 `TAG_FLOAT=6`
    （`(data_offset<<3)|6`，f64 存于 linear memory）：常量进数据段（`abi.float_value` +
    `emit._StringPool.intern_float`），运行时用 bump arena（2 MiB 起）承接运算结果，
    `runtime.js` 增 `pyFloatRepr`（与 TS 宿主一致）、`+ - * / < > =` 的 f64 语义与 float 格式化。
    顺带修复 wasm runtime 的 `display`/`echo` 返回 `nil` 的问题（VM 返回被打印值）——
    现在 `(display (+ 1.5 2.5))` 三处输出与 register VM 一致。探针 `build/probe_wasm_float.py`
    16 例（11 ok + 4 未支持 + 1 输入笔误）；补 `tests/test_wasm_backend.py` 结构性 + 端到端用例，
    更新 `docs/wasm-backend.md`（tag 表 + 支持列表）。
59. ✅ **Go full case mapping（本轮）**：Go 标准库只有 simple case mapping 且 Unicode 版本（17.0）
    比参考实现 Python 3.12（15.0）新，`string-upper`/`string-lower` 与 Python/JS 不一致
    （`ß`、`ﬁ`、`İ`、`ǰ`、Final_Sigma……）。新增 `qy/backend/golang/pkg/stdlib/unicase.go`：
    由「Python `str.upper()/lower()` vs Go simple mapping 的逐码点差集」生成 157+56 条
    覆盖表 + Final_Sigma 上下文规则，`fullUpper`/`fullLower` 替代 `strings.ToUpper/ToLower`；
    `char-upcase`/`char-downcase` 改用 full mapping 并校验「恰好一个 scalar」（对齐 Python 的
    `QY_RUNTIME_ERROR`，TS 侧同步修多字符返回）。矩阵：case 12 例 + 版本差异 10 例 + sigma 10 例 +
    char 5 例全部三宿主一致；补 Go `unicase_test.go` 与 Python 回归；`docs/hosts.md` 移除该限制。
60. ✅ **wasm raw-argument 字面量解析（本轮）**：wasm emitter 的 `_load_host` 之前遇到
    `Symbol` 常量直接报 `LOAD_HOST with unsupported value`，导致 `(display 1)` 等最基本的
    raw-argument 用法在 wasm 不可用。现在对 literal spelling 用
    `qy.session.pre_ss.resolve_default_literal` 在编译期折成 value（wasm 没有 symbol 值 tag），
    非字面量 symbol 仍显式报错。探针 `build/probe_wasm_raw.py`：`(display 1)`→`11`、
    `(display 3.14)`→`3.143.14`、`(echo 42)`、`(display "hi")`、`(display #\a)` 等 9 例与
    register VM 一致；补 `tests/test_wasm_backend.py` 端到端用例并更新 `docs/wasm-backend.md`。
61. ✅ **wasm heap 对象：symbol / chain（本轮）**：新增 `TAG_HEAP=7`（linear memory 对象，
    首 i32 子 tag：`1` symbol、`2` cons）；`emit._ConstantPool` 增 `intern_bytes/intern_symbol/
    intern_cons`，`_load_host` 收敛为单一 `_encode_value`（symbol 先按字面量规则折值，其余成
    heap symbol；chain 递归构建 cons）；`runtime.js` 增共享 bump arena、`cons`/`car`/`cdr` 与
    heap/symbol/chain 的 `format`（含点对链）。至此 wasm 支持 quote 数据：validation 例子
    **4→5/10**（`01_quote_chain.qy` 通过），探针 11 例（含 `(cons (car '(alpha beta)) (cdr '(alpha beta gamma)))`、
    `'(1 . 2)`、嵌套链、`(display 'sym)`）与 register VM 一致；补结构性 + 端到端用例并更新文档。

剩余跨宿主差异（非阻塞，记录于 `docs/hosts.md` §5）：Go `parallel` 顺序执行、
`read-int` 返回 nil、`RUNTIME_EVAL` 极简；TS `RUNTIME_EVAL` 仅子集、同步 `race`
胜者可能与 asyncio 不同；TS/Go 模块面暂不含 `qy.legacy`。

# 9½. 自举解释器进展（meta-interp）

目标：用 Qy 写一个能解释 Qy 的解释器，最终达到自举。当前真源在 `meta-interp/main.qy`。

## 已完成

- **Reader**：`tokenize-string`（含 `;` 行注释、字符串转义 `\n \t \r \" \\`、
  三重引号字符串）、
  parser 产出 symbol / chain / number（含负数）/ string / nil。
- **环境模型**：env 是 frame chain；closure body env 允许一个 `(FALLBACK globals)` 头帧，
  用来解析"定义晚于闭包创建"的前向引用/互递归（对应语言里 pre-declared binding slot 的语义）。
- **求值器**：CPS + 显式 continuation/handler 上下文；`quote` `if` `cond` `define`
  `defun` `lambda` `let` `and` `or` `from` `apply` `pipeline` `module` `exports`
  （含 `import name as alias`）、`macro`/`quasiquote`/`unquote`/`unquote-splicing`、
  **宏 hygiene**（`hygienize`：binder 重命名 + definition-site free symbol 绑定 +
  `capture` 解包 + `gensym` 新名，见 `meta-interp/main.qy` 的 §macro hygiene）、
  `eval`/`reify`（最小实现）；
  primitive 表覆盖
  `+ - * / mod = == < > <= >= car cdr cons list null? not eq? eq atom len truthy is print`；
  其余宿主算子通过 `lookup-export` 透传（`(eq (type f) 'operator) (apply f vals)`）。
- **代数效应**：`defeffect`/`perform`/`handle`/`resume` 在 Qy 内部实现。
  handle 在动态上下文压入 handler 记录；perform 捕获从 perform 点到该 handler
  边界的 delimited continuation（CONT 值）；resume 把 continuation 重新注入，
  经 resume-target 栈在 handler 边界弹回，支持 handler 在 resume 后继续计算
  （continue 语义）。未处理效应 / 不可恢复 resume 走 `raise-error`。
- **闭包**：具名闭包支持自递归；`from`/`apply` 已接入。
- **输出对齐**：求值与打印分离（先全部求值再按 `qy run` 顺序打印）；`print-value`
  走宿主 `display`，不对字面量拼写做二次解析。
- **CLI**：`qy run meta-interp/main.qy -- FILE...`（支持多文件批量）；无参数时运行内置 self-test。

## 验证

- `bash meta-interp/compare.sh`（省略参数即跑全部用例）：**19/19** 与 Python VM 输出逐字节一致；
- `QY_META_SELF=1 pytest tests/test_meta_interp.py::test_meta_interp_interprets_its_own_source`：
  解释器解释自身源码后仍能正确解释内层程序（约 30s，默认跳过）；
- 两者统一由 `make test-selfhost` 验证，并已纳入 `make ci`；
- `tests/test_meta_interp.py` 另外在 pytest 里对 `meta-interp/cases/*.qy` 与
  `examples/qy/validation/*.qy` 做逐字节对拍。
- `tests/test_meta_interp.py`：
  - 19 个 `cases/` 用例默认运行，逐字节对比参考；
  - `tests/qy` 全部 56 个行为用例在一次解释器进程内批量对拍；
  - `examples/validation` 8 个验收样例默认对拍（03/09 深尾递归压力样例默认跳过，
    含 08_host_interop：py 扩展边界 + triple-quoted reader）；
  - `QY_META_SELF=1` 时额外运行阶段 2 自解释测试（解释器源码被自身解释后仍能把
    `(+ 1 2)` 解释为 `3`）。

## 已知差距

- `this`/`slot`/`bind` 为可运行近似（local binding），不建模真正的 symbol-space
  object / binding slot；`component` 只作为不融合的占位值。host 对象在文本表示上
  已统一为 `<symbol-space>` / `<slot>`（见 §9¾ item 17），三宿主对 `hello.qy` 逐字节一致。
- `reify` 对 host reference 的 partial 语义未实现。
- 效应的已知简化：`divide-by-zero` 等 host 算术效应按宿主行为使用 identity
  continuation；显式 `perform` 支持 multi-shot（`19_multishot`），但并发结构与
  effect 的交互未验证；`parallel`/`all`/`race` 为顺序实现（语言允许）。
- number family 只透传 host 数字；定宽整型/浮点的 concrete 类型语义未在解释器内建模。
- 性能：CPS 化后阶段 2 自解释正确但仍极慢（约 37s 跑完单次自解释测试）；
  瓶颈在解释执行本身、闭包分配与全局 lookup 的线性扫描，需要专门优化。
- 环境用不可变 chain 建模，前向引用依赖 FALLBACK fallback；尚无 `set!`/mutation
  语义（语言核也刻意不提供）。

---

# 9¾. 宿主边界与扩展机制（qy/ext）

目标：Qy 语言内核独立，宿主支持全部经标准扩展机制进入语言，二者界限清晰。

## 已落地

- `qy/ext/`：`ExtensionDescriptor` / `ExtensionCapability` / `ExtensionBinding`
  声明模型 + 注册表（`descriptor.py` / `registry.py`）。
- 内核 `qy.core` 不再混入宿主算子；容器构造器更名 `container_operators`
  （产物是 Qy 语义值）。
- `ExtensionPolicy`：扩展/capability 准入检查（`load_extension(policy=...)`），
  违反抛 `QyCapabilityError`；`extension_requires(name)` 提供声明查询。
- 模块迁移（module_name 保持兼容）：
  - `qy.symbol_space.python` → `qy.ext.python`（`qy.py`，capability `python-exec`）；
  - `qy.symbol_space.testhost` → `qy.ext.testhost`（`qy.testhost`）；
  - `read-file` 从 `qy.io` 移入 `qy.ext.fs`（capability `filesystem`）；
  - 自举解释器的通用宿主能力拆出 `qy.ext.interp`
    （`cli-args`/`lookup-export`/`display`/`raise-error`/`gensym`）；
  - `.py` 文件模块加载从 `qy/import_/registry.py` 移入 `qy.ext.python-modules`，
    内核只保留通用 `register_file_module_loader` hook。
- `HostObjectRef` 定义移入 `qy.sem.host.HostReference`，VM instance 只重导出。
- 字符串字面量解析为 `StringValue`：语言运行时不再以宿主 `str` 定义字符串值；
  Python 扩展在边界显式 `StringValue <-> str` / `NumberValue <-> int|float` 转换。
- `qy.sem.convert.to_qy_value` / `from_qy_value`：扩展边界的统一宿主值转换
  （未知对象 → `HostReference`）；`string-split`/`string->list` 返回 `TupleValue`。
- `parallel`/`all` join 结果为 `TupleValue`；`len`/`get`/`has?`/`append`/`chain`
  不再接受裸宿主容器；语义容器补宿主级 permissive `__eq__`。
- `tests/test_extensions.py`：内核包不得 import `qy.ext.*` / 宿主模块；
  扩展声明与 capability；扩展模块装载；`qy.core` 无 `py`；`qy.io` 无 `read-file`。
- 文档：`docs/extensions.md`；`docs/package-structure.md` 增补 `ext/` 所有权与导入方向。

## 待迁移

- 宿主侧显式 `env.define` 注入裸宿主容器仍是允许的边界行为（VM 不自动转换）；
  后续可在实例/profile 层增加 canonicalize 策略。
- `qy.project` / CLI 对文件系统、进程、时钟、网络的访问，逐步建模为显式扩展
  capability（`filesystem` / `process` / `clock` / `network`），实例按 profile 选择启用。
- `qy.ext.testhost` 仍含 `run-file`/覆盖率等测试专属能力；`run-file` 直接调用
  `AsyncQy` 求值，后续应改为显式 build/求值 capability。
- 错误文本/对象 repr 中残留的宿主细节（`<qy.session.runtime_space...>` 等）。

---

# 10. 结束条件

项目进入下一阶段前，至少应达到：

- 文档与实现不再分别描述两个语言；
- runtime object model 不再依赖 Python 偶然性质；
- IR 三层各自可独立解释、验证、演进；
- evaluator 不再承担核心语义；
- qytest 成为语言行为验收面；
- register VM 可以被视为真正唯一后端，而不是“主路径 + 旧解释器阴影”。
