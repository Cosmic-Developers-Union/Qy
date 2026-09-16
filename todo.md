# Qy Full Roadmap

本文件不是最近一批工作的便签，而是 **Qy 从当前实现走到目标语言的完整路线图**。  
历史批次与已完成细节看本文档 §2 与 git log；语言规范看 `LANGUAGE.md`；算子分层看 `docs/op.md`；阶段边界与 IR 约束看 `docs/pipeline.md`、`docs/ir-design.md`。

最近一次本地基线（本轮整改后）：

- `uv run python -m pytest -q`：1056 passed, 1 skipped（skip 为 `QY_META_SELF=1` 才运行的自解释慢测试）
- `uv run ruff check .`：passed
- `uv run ruff format --check .`：passed
- `uv run ty check .`：**0 diagnostics**（本轮清空）
- `uv run qy check examples/hello.qy`：ok（analyzer 已改为 canonical frontend + HIR verifier）
- HIR verifier 在 `examples/hello.qy` 与 10 个 validation 样例上 clean（H1–H14）
- qytest `tests/qy` **54/54**、`examples/validation` 10/10 通过；CLI 6 阶段 dump + run/fmt/export/llvm 全部可跑
- `make libqy` / `make llvm-gen` 可用；LLVM IR 仍不能通过 `llc`（见 §8½）
- `qy/sem` 已不 import `qy.vm`；legacy `UserFunction` 求值路径移至 `qy/vm/instance/legacy_eval.py`
- `rg QY_DELETE_AFTER qy`：7 处标记（stdlib shim、sem bridge、analysis infer/scope/refs、frontend tuple 兼容层）

历史基线（2026-09-14）：

- `uv run python -m pytest -q`：1048 passed, 1 skipped（skip 为 `QY_META_SELF=1` 才运行的自解释慢测试）
- `uv run ruff check .`：passed
- `uv run ruff format --check .`：passed
- `uv run ty check .`：48 diagnostics（`qy/cli/commands/pkg.py` 等既有问题，非本轮引入）
- 宿主边界：`qy/ext/` 扩展机制落地；`tests/test_extensions.py` 边界测试 7 项通过
- `meta-interp/cases/` 19 个自举用例与 `qy run` 参考输出逐字节一致；
  `tests/qy` 行为用例 **54/54**、`examples/validation` 8 个验收样例全部对拍通过
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
    与空的 `passes/surface/`；`closure.convert` 是唯一保留的未实现 pass；
  - 优化接线：`PipelineOptions.optimize` + `optimize.mir` 接线点接入默认管线
    （默认 False），优化顺序真源收敛到 `passes/optimize/apply.py::OPTIMIZE_PASSES`；
    实测 86 个语料在开启优化后有 46/86 行为不一致（仅简化子集已 28/86），
    因此**不默认开启**，证据记录在 docs/package-structure.md §3.1；下一步是让
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
- `pre-symbol-space-chain` 仍更像展平 root + literal resolver；
- module / fold 存在多条近似实现路径；
- compile-time env 仍只是 runtime env facade；
- LIR 仍较薄，未完全承担低层职责；
- register VM 仍承担较多 host-call compatibility；
- legacy operator dispatch (`legacy_user_function.py` 等) 与 `sem/runtime.py` 的 `UserFunction`/`ComponentOperator` 并存，
  部分尾调用仍走旧 evaluator 路径；
- `io`、`truthy`、runtime identity 仍未落地；`reify` 已有最小实现（partial、ScopeOperator、无 effect 路径）。

## 2.3 当前主要事实漂移

1. ~~`qy/frontend/form.py` 的 `Form` 联合包含 tuple / `SpannedTuple` / `DottedTuple`，
   `TupleAtom` 包含 `str | int | float | bool | bytes | None`；兼容 API 暴露 Python tuple。~~
   ✅ 已闭合：`qy/frontend/form.py` 已删除；`Symbol` / `Chain` / `QyNil` / `Form` 与
   `get_span` 的真源是 `qy/core/syntax.py`；`Form = Symbol | Chain | QyNil`；
   `form_to_tuple` / `TupleForm` / `read_tuple` / `write_tuple` / `SpannedTuple` /
   `DottedTuple` 全部删除（含公共导出）；`surface.py` 的 tuple 版实现已删；
   `macro/hygiene.py` 改为 chain 表示并保留 span。
2. ~~quoted literal 已在 reader 阶段变成 Python `str`（`_decode_string_symbol` 经
   `ast.literal_eval` 解出），兼容 API 入口。~~ ✅ 兼容入口已删除；
   仅剩 MIR/HIR 侧 `_quote_data` 的物化尾巴，见第 7 条。
3. ~~`qy/sem/core.py` 里的 `ChainValue` 与 `qy/core/syntax.py` 的 syntax `Chain` 并存。~~
   ✅ 已闭合：`qy.sem` 不再定义 datum 或 Qy 自身对象；`NIL` / `NilValue` / `SymbolValue` /
   `ChainValue` / `DatumValue` 删除；`nil` / `T` / `none` 同处 `qy/core/syntax.py`；
   迁移期桥接层 `qy/sem/bridge.py` 已删除。
4. `literal_resolver` 让 `1` 等 spelling 绕过了真正的 chain / fold 模型；
5. `(define 1 10)` 的行为尚未由最终 root 模型解释；
6. `qy.core` 仍混入 profile / compat 能力；
7. 标准数据算子已返回 Qy `TupleValue` / `ListValue` / `DictValue` / `SetValue`，但
   `mir/normalize._quote_data`、`session/pre_ss.try_default_literal` 仍会把 quoted
   string / number 物化成 Python `str` / `int` / `float`；reader/string literal 仍有 Python `str` 迁移尾巴；
8. `eq` 已脱离 Python identity / interning，后续还需补完整结构相等算子；
9. `cond` 已是 nil-only truth；标准 profile 的 `truthy` 负责复杂真值；
10. `truthy` 已有正式 operator，但还需按 profile 层文档继续收口；
11. `io` 仍只是 `print/echo` 模块，不是 Qy runtime model；
12. `reify` 已有最小实现（ScopeOperator、partial-failure、无 effect 路径）；
13. `HostObjectRef` 尚未演化成完整 host reference / runtime identity 容器；
14. macro compile-time evaluator 已脱离 bytecode / register VM；compile-time namespace 仍需继续显式化为独立 slot/layout；
15. `from` 在 stdlib / VM / source-module 路径没有完全共用实现；
16. ~~`quasiquote` nested 路径仍依赖过时 `list/append` 假设。~~ ✅ 已闭合：
    quasiquote 展开统一到 `qy/core/quasiquote.py`（macro expand 与 HIR lowering 共用一份实现），
    不再有第二份 tuple 版实现；
17. 默认 LIR 仍以 compat dialect 为主，但主 pipeline 已执行 `mir.validate` / `lir.verify`，bytecode emit 会拒绝非 VM compat opcode；
18. LIR 已在 abstract-machine dialect 下显式建模 handler frame / continuation frame / symbol-space / binding slot：`lower_effects` + `passes/lir/spaces.py` 产出 `frame_layout` / `handlers` / `continuations` / `symbol_spaces`，并把 `ENTER_SCOPE`/`DEFINE_ONCE` 降成 `SS_ENTER`/`SS_LEAVE`/`SLOT_COMPLETE`，因此 L5–L12 verifier 在 abstract-machine dialect 下全部有数据（L11/L12 CFG-aware）；仍缺 virtual stack 的运行时语义、HIR 层 `resolve.spaces`（当前 layout 由 LIR 从指令流重建），且 VM 尚不执行抽象机 opcode；
19. effect frame 仍主要由 VM 中的 Python 对象承担；
20. pending-binding / incomplete-value effort 尚未实现；
21. legacy `UserFunction` 仍是 `lambda`/`defun` 的 Python callable 表示，其求值路径已从 `qy/sem/runtime.py` 移到 `qy/vm/instance/legacy_eval.py`（`sem` 不再反向依赖 `vm`），但尚未收敛到 bytecode function；
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
   - `UserFunction` -> bytecode function；
   - evaluator 退场；
   - compat stdlib 下沉。
6. **自举解释器推进**
   - 保持 `meta-interp/cases/` 与受支持 `tests/qy` 用例的对拍；
   - 逐步补齐 py 宿主互操作、number family 的 concrete 类型语义；
   - 性能：消除解释器全局 lookup 的线性扫描，再谈阶段 3 自解释。

---

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
  （含 `import name as alias`）、`macro`/`quasiquote`/`unquote`/`unquote-splicing`
  （非 hygiene；`gensym`/`capture` 未实现）、`eval`/`reify`（最小实现）；
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

- `meta-interp/compare.sh cases/*.qy`：19/19 与参考输出逐字节一致。
- `tests/test_meta_interp.py`：
  - 19 个 `cases/` 用例默认运行，逐字节对比参考；
  - `tests/qy` 全部 54 个行为用例在一次解释器进程内批量对拍；
  - `examples/validation` 8 个验收样例默认对拍（03/09 深尾递归压力样例默认跳过，
    含 08_host_interop：py 扩展边界 + triple-quoted reader）；
  - `QY_META_SELF=1` 时额外运行阶段 2 自解释测试（解释器源码被自身解释后仍能把
    `(+ 1 2)` 解释为 `3`）。

## 已知差距

- `this`/`slot`/`bind` 为可运行近似（local binding），不建模真正的 symbol-space
  object / binding slot；`component` 只作为不融合的占位值，host 对象 repr
  （RuntimeSpace / slot）无法逐字节对齐，因此 `examples/hello.qy` 未纳入自动对拍。
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
- `qy.sem.bridge.to_qy_value` / `from_qy_value`：扩展边界的统一宿主值转换
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
