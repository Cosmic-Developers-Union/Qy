# Qy TODO

本文件只保留**当前事实**、**未闭合问题**、**下一步顺序**。历史批次统一看 `report.md`。  
最近一次本地基线（2026-05-17）：

- `uv run python -m pytest -q`：363 passed
- `uv run ty check .`：passed
- `uv run ruff check .`：passed
- `uv run python -m qy test.qy tests/qy`：40 / 40 passed
- `uv run python examples/run_validation.py`：10 / 10 passed
- `uv run qy test.qy tests/qy`：当前环境仍未形成可靠验收，需单独收口 console-script 入口

## 0. 不可漂移的契约

- Qy 是 Python 实现的 like-Lisp；核心目标是 algebraic effects + register VM。
- 唯一管线：`source -> raw AST -> surface dialect -> macro expand -> HIR -> MIR -> LIR -> bytecode -> register VM`。
- syntax datum 只有 `symbol` 与不可变 `chain`。
- 语法只有 S-expression；`form` 只是单个 S-expression 单元，不是第三类语法对象。
- runtime value 是 Qy 语义对象，抽象上由 `number`、`string`、`object` 构成；`nil` / `t` 是 Qy 自身对象。Python value 只是宿主互操作对象，不能与 runtime value 混淆；host reference 是一等 runtime value。
- symbol 求值沿 symbol-space-chain 查找；同一 symbol-space 不可重绑定。
- `define` 只检查当前空间，可 shadow 链上后续空间；`let` 创建新空间，可绑定任意 symbol。
- `pre-symbol-space-chain` 不是语言核目标，但它是标准实现起点；reader、analyzer、LSP、lowering、runtime 必须读取同一 `Qy` 实例事实。
- chain 只负责 lookup；fold 才把 binding 吸收到目标 symbol-space。`from` 是受 `exports` 约束的选择性 fold。
- module 是具名 symbol-space；`exports` 是可供外部 fold 的 export view。
- 核心 form：
  - `quote`
  - `atom eq car cdr cons`
  - `define let cond`
  - `pipeline parallel all race`
  - `defun lambda apply`
  - `macro quasiquote unquote unquote-splicing gensym capture`
  - `defeffect perform handle resume`
  - `module from import exports`
- `pipeline` 串行；`parallel` 只表示“允许并行”且支持 effect；`all` 是 barrier continuation；`race` 是 first-resume-wins。
- `cond` 只把 `nil` 视为 false；`truthy` 是 standard profile 的复杂判断算子，负责按自身规则返回 `t` / `nil`，不建立全局宿主值自动转换。
- `read` 只产出 syntax datum；`eval` 把 syntax datum 变成 runtime value；`reify` 把 runtime value 在目标上下文中投回 syntax datum，默认只要求等价回环，不默认承诺 identity round-trip。
- 默认 surface dialect 只提供静态可描述的 `'x`、quasiquote 内 `,x` / `,@x`；不实现 unrestricted reader macro。
- register VM 是唯一 runtime backend；不得重新引入第二执行后端。
- 新增 operator 前先判断能否用 Qy 本身实现；能自举的能力优先留在 Qy library。

## 1. 当前进度判定

### 已完成

- register VM 已成为唯一公开执行路径；`qy.ir_vm/`、`python_codegen.py` 已删除。
- `raw AST -> surface dialect -> expand -> HIR -> MIR -> LIR -> bytecode -> VM` 主链已打通。
- `pipeline` / `parallel` / `all` / `race` / `apply` / effect 已进入主 pipeline。
- runtime `string` 已落地；字符串字面量不再冒充 `Symbol`。
- `eq` 已收口为 identity 语义；数值等值由 `=` 一类算术算子承担。
- macro 已有独立 expand 阶段、hygiene、namespace、trace、source map 的基础实现。
- CLI 已能查看 `ast` / `expand` / `hir` / `mir` / `lir` / `bytecode`。
- `Environment.fold_from()` 已落地；stdlib `from` 路径已开始使用 fold 语义。
- `Qy.pre_symbol_space_chain` 已有只读快照入口。
- LSP 已跟随具体 `Qy` 实例，并合并 macroexpand / analyzer diagnostics。
- qytest 已从样板推进为 40 个行为用例；pytest 与 qytest 已形成分工。
- benchmark 已按当前 pipeline 重建 phase，并补入 `module-import` / `effect-heavy` / `macro-heavy`。
- `evaluator.py` 已退出主求值路径，当前只剩兼容面与旧 helper。

### 仍在过渡

- **pre-symbol-space-chain**：已有快照，但标准实现仍更像“单个展平 root + literal resolver”，还没有把 profile 链、fold 计划、root local membership 建模完整。
- **profile 分层**：已有 `STANDARD_PROFILE_MODULES` / `OPTIONAL_STDLIB_MODULES`，但 `qy.core` 仍默认携带 arithmetic，`qy.num` 的 optional 身份还没有真正变成行为边界。
- **module / fold**：stdlib `from` 已走 `fold_from()`，但 VM 与 source-module 路径还没有统一到同一实现。
- **macro**：展开已独立，compile-time facade 仍基本复用 runtime 环境，capability / effect policy 没有真正隔离。
- **LIR**：已有 register layout、跳转修正、简单 peephole，但还没有承担 effect frame、ABI lowering、layout/rerank 等真正低层职责。
- **VM / TCO**：已有虚拟寄存器执行、自尾递归与 continuation 恢复；互递归、effect 边界下 tail call、显式 frame layout 仍未完成。
- **legacy**：`evaluator.py`、`eval_runtime.py`、legacy operator dispatch 仍被 stdlib 与测试依赖。
- **strings stdlib**：runtime `string` 已正式化，但旧 `str-*` 仍在 compat 层，且部分行为仍把 `Symbol` 当文本。

### 当前最重要的事实漂移

1. `pre-symbol-space-chain` 文档语义已经领先于实现；`Qy().pre_symbol_space_chain` 目前仍只有一个展平节点。
2. `(define 1 10)` 仍可在默认 root 成功，因为数字 spelling 仍是 resolver fallback，而不是已 fold 的本地 binding；这说明 root fold/profile 模型还没闭合。
3. `qy.num` 已出现，但 arithmetic 仍经 `qy.core` 进入默认 profile；“语言核 / standard profile / optional stdlib” 仍是半拆层。
4. `from` 的 fold 语义在 stdlib、VM、source module 三条路径没有完全共用实现。
5. `compile_time_environment()` 仍只是 facade，不是独立 compile-time symbol-space / capability 模型。
6. **已确认偏移**：raw AST 只能有 `symbol` / `chain`，但 `reader.Form` 已直接包含 `str`，quoted literal 也直接读成 Python `str`。这不是允许的 parser-level 例外，而是阶段职责错误。
7. `quasiquote` 仍在 nested 路径展开出 `list` / `append`；默认 profile 没有 `list`，当前 `(quasiquote (quasiquote ...))` 已会因 unresolved `list` 失败。这说明 macro surface 仍依赖过时 stdlib 假设。
8. `qy.core` 当前不只暴露 `atom/eq/car/cdr/cons`，还暴露 `chain/append/get/has?/is/len/type` 等非最小核心能力；同时 analyzer / semantics 仍把 Python `list/tuple/dict/set` 当命名类型处理。若这些只是 host object 细分，就不应继续漂成语言核类型面。
9. 标准实现仍缺少一个明确的 `io` runtime model；`echo` 目前只是孤立便利算子，无法承接后续 Python / Go 生态接入。
10. `truthy` 已被确认需要存在，但其真值协议、host reference 适配边界、与 `if` 的关系还没有写成正式设计。
11. 当前实现仍把 Python identity 泄漏进 `eq`，例如小整数 interning 会影响结果；Qy 还没有自己的 runtime identity / `id` 模型。
12. `reify` 尚未建模；host reference 也还没有“显式实现或 perform effect”的协议。
13. 自定义 operator 目前缺少正式声明协议；若作者不能补充 arity、参数策略、返回类型、effect 等元数据，analyzer / LSP 无法可靠理解它。
14. `docs/language-core-audit.md` 对 B2 的完成状态与正文仍存在自相矛盾。
15. exact shell 入口 `uv run qy ...` 仍未作为可靠验收面闭合。

## 2. 下一步顺序

### P0-1. 闭合 symbol-space / profile 根模型

- 先修正 reader / raw AST 边界：
  - raw AST 只允许 `symbol` / immutable `chain`；
  - number / string spelling 不得在 reader 阶段变成 runtime value；
  - surface dialect 只能做 spelling rewrite，不得替后续阶段承担 literal 求值。
- 把 `pre-symbol-space-chain` 从“可读快照”推进为真实初始链：
  - 明确 standard profile、literal layer、stdlib layer、host injection layer 的节点顺序；
  - 明确哪些节点只参与 lookup，哪些 binding 会在 module root 初始化时 fold；
  - reader、analyzer、lowering、LSP、runtime 只能读取实例链，不再各自推断。
- 固定 root define 规则：
  - 能否 `define` 只看 current head local membership；
  - 数字 / 字符串 spelling 若已被 fold 到 root，则同层 define 必须失败；
  - 若只在后续链节点，则 current head 可 shadow。
- 把 module root 初始化、`from`、`exports`、profile bootstrap 全部表述成同一套 chain + fold 规则。
- 加一致性测试：
  - root define / child shadow；
  - host 注入层；
  - number / string spelling；
  - analyzer / lowering / runtime / LSP 同源。

**完成标准**：同一 `Qy` 实例下，绑定可见性、可重定义性、diagnostics、运行时结果完全一致；`pre-symbol-space-chain` 不再只是描述词。

### P0-2. 真正拆开 core / standard profile / optional stdlib

- 固定三层：
  - 语言核：不可替代的 core form；
  - standard profile：默认 `Qy()` 预装能力；
  - optional stdlib / host capability：显式引入能力。
- 决定 arithmetic 的正式归属：
  - 若默认加载，写成 standard profile 事实；
  - 若显式导入，真正从 `qy.core` 移出；
  - 无论哪种，都不能再把 profile 便利性写成语言核。
- 收口 operator metadata：
  - core / profile / optional / compat 分层；
  - arity、argument policy、return type、effect、tail transparency 只保留一个真源；
  - analyzer、lowering、CLI、runtime 读取同一模型。
- 旧 `str-*` 停止扩张；围绕 runtime `string` 重新设计 `qy.str`。
- 让 default surface dialect、`unquote-splicing`、operator 文档三者保持一致。
- 设计 Qy 自己的 `io` runtime model：
  - 先定义 Qy 层的 `io` 能力边界，而不是让 Python file object 反向定义语言；
  - 明确它位于哪一段 `pre-symbol-space-chain`；
  - 明确 stdin / stdout / stderr、stream、file、buffer 等最小模型；
  - 明确哪些能力属于 `io`，哪些应拆给 `fs` / process / network；
  - 明确 `echo` 是否只是基于 `io` 的 Qy 级便利算子；
  - Python / Go 等宿主只提供 adapter，后续生态接入复用同一 runtime model。
- 正式设计 `truthy`：
  - 保持 `cond` 只认 `nil`；
  - `truthy` 自己决定复杂真值判断并返回 `t` / `nil`；
  - 明确 `if` 等扩展控制算子是否以它为基础；
  - 不引入全局 Python value 自动转换规则。
- 闭合 runtime value / Python value 边界：
  - 文档、类型系统、analyzer 不再把 Python value 直接当作 Qy 语义定义；
  - Python / Go 仅提供实现或 adapter，host reference 才是进入 Qy runtime 的语义对象；
  - 重新审计 `True` / `False` / `None`、`list` / `tuple` / `dict` / `set` 的文档和类型位置。
- 设计 Qy runtime identity：
  - `eq` 比较 Qy identity，不依赖 Python `id()` / `is`；
  - 明确哪些 value 自带 runtime identity，host reference 如何获得稳定 identity；
  - 若提供用户可见 `id`，其稳定范围只能由 Qy runtime 契约定义，不能泄漏宿主地址语义。
- 设计 `reify`：
  - 区分可求值表示、等价回环、identity 回环三种强度；
  - 默认契约采用等价回环；
  - identity 回环只能依赖 binding / handle / context；
  - host reference 必须显式实现 reify 或 `perform` 对应 effect；
  - `display` / `write` / `reify` / `eval` 不得混为一类。
- 定义自定义 operator 的声明协议：
  - 创建者必须能声明 arity、argument policy、argument types、return type、effects；
  - 视需要声明 compile-time、runtime-meta、tail transparency 等属性；
  - analyzer、LSP、CLI docs、runtime 统一读取同一份声明；
  - 声明不完整的 operator 只能退化为低精度 `any` / unknown，而不能由工具链臆测。
- 重新审计 `qy.core` 的实际 exports：
  - 核心 chain 面只允许 `atom/eq/car/cdr/cons`；
  - `chain/append/get/has?/is/len/type` 若保留，必须明确归入 profile / stdlib / compat；
  - Python `list/tuple/dict/set` 若只是 host adapter，不应继续伪装成语言层基本类型。

**完成标准**：给定一个 profile，默认可见符号集合、CLI `operators`、静态分析、runtime 四方一致。

### P0-3. 完成 macro，而不是继续扩外壳

- 让 compile-time symbol-space 成为真模型：
  - definition-site binding；
  - module macro import/export；
  - capability / effect policy；
  - diagnostics / source map / LSP 消费。
- 保持 surface dialect 有限、静态、可枚举；若 reader 继续增长，把 dialect 转换从 `reader.py` 拆出。
- 用 qytest 补齐：
  - quasiquote / splice；
  - hygiene；
  - `capture`；
  - module macro import；
  - expansion failure / source map。
- 清掉 quasiquote 对过时 `list` 假设的依赖；嵌套 quasiquote 必须只依赖当前语言面可保证的构造能力。

**完成标准**：macro 不再借 runtime 环境“顺手可用”，而是拥有独立、可分析、可约束的 compile-time 语义。

### P0-4. 统一 fold / module 实现路径

- 让 `from` 在 stdlib、register VM、source module 三条路径共享同一 fold primitive。
- 明确导入冲突、exports 过滤、重复 fold、同层 define 冲突的单一规则。
- 把 `docs/language-core-audit.md` 中 B2 状态修正到与实现一致。

**完成标准**：模块导入不再有三套近似实现；文档、静态分析、runtime 使用同一套判定。

## 3. P1：把低层执行体系做实

### P1-1. LIR 真正承担低层职责

- MIR 只保留 CFG、virtual register、tail position。
- LIR 接管：
  - instruction selection；
  - physical register layout / allocation；
  - effect frame layout；
  - host-call ABI lowering；
  - block layout / rerank；
  - jump fixup；
  - peephole / copy cleanup；
  - debug span / trace injection。
- `bytecode_compiler.py` 只做最终结构转换，不重新解释高层语义。

**完成标准**：每类 rewrite 都能指出唯一所属层，`LIR -> bytecode` 不再近似直接复制。

### P1-2. continuation / effect / virtual stack

- 把 effect frame、handler frame、resume token、parent continuation 显式下沉到 LIR / bytecode。
- 固定 `parallel` / `all` / `race` 在 effect 下的 continuation 合流规则。
- 继续推进：
  - mutual recursion TCO；
  - effect 边界下 tail call；
  - Python call stack 完全退出语义依赖。

**完成标准**：effect + tail call + ordering/join 组合能直接从 LIR / bytecode 解释。

### P1-3. 删除 legacy 承担的语义

- `evaluator.py` 只能继续减，不允许新增语义。
- `eval_runtime.py` 降为兼容 facade，逐步清空真实职责。
- legacy operator class 只保留 host adapter 身份，不再承担 core semantics。
- 把 stdlib 与测试逐步迁到正式 metadata + VM 路径。

**完成标准**：新增核心语义不再要求同时修改 evaluator 与 VM 两套实现。

## 4. P1：qytest 与测试分层

- 固定长期分工：
  - `pytest` 验证 Python 实现、各编译层、诊断、回归；
  - `qy test.qy tests/` 验证 Qy 语言行为契约。
- qytest 的 host capability 保持最小：
  - 读文件；
  - 列目录；
  - 路径判断；
  - CLI args；
  - 其他 assertion、reporting、DSL 优先由 Qy 自举。
- 下一批行为用例重点：
  - `pre-symbol-space-chain` / fold / shadow；
  - profile 差异；
  - macro failure path；
  - `parallel` / `all` / `race` + effect；
  - module export conflict；
  - runtime string 与新 `qy.str`。
- 收口 exact console-script 入口验收，不能只测 `python -m qy`。

## 5. P2：文档、基准、复杂度

### 文档

- `LANGUAGE.md` 是唯一语言真源；其他文档只做导读、设计注记、审计。
- 立即修正：
  - `docs/language-core-audit.md` 的 B2 状态矛盾；
  - 与旧 pss、旧 imports、旧 string 语义、旧 raw AST 形状相关的残余说法。
- examples 只保留验证当前契约的样例；只解释过渡实现的样例删除。

### benchmark

- 继续只保留 register VM 维度。
- 当前 phase 已对齐；下一步补：
  - 历史趋势记录；
  - 可解释的 regression 阈值；
  - 决定是否接入 CI gate。

### 复杂度

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

- 先拆职责，再加分支。
- `evaluator.py` 只能减，不能加。
- 新模块必须对应真实边界，不得只搬运复杂度。
- 每批 `report.md` 必须记录：
  - 目标；
  - 修改范围；
  - 新增 / 删除文件；
  - 复杂度变化；
  - 仍未删除的 legacy 面；
  - 验证命令与结果。

## 6. 删除 / 降级清单

- 已删除：`qy.ir_vm/`、`python_codegen.py`。
- 待删除或降级：
  - `evaluator.py` 剩余语义；
  - `eval_runtime.py` 兼容面；
  - legacy operator dispatch 对 core semantics 的承担；
  - 旧 `str-*`；
  - 只验证过渡实现的 examples / tests。

## 7. 批次要求

- 每批只推进一个主题：`symbol-space`、`profile/stdlib`、`macro`、`module/fold`、`LIR`、`VM/effect`、`qytest`、`docs`。
- 行为变更必须同步核对：
  - `LANGUAGE.md`
  - `docs/op.md`
  - `docs/pipeline.md`
  - `docs/language-core-audit.md`
  - `AGENTS.md`
  - `CLAUDE.md`
  - `todo.md`
- 默认验证：

```bash
uv run python -m pytest -q
uv run ty check .
uv run ruff check .
```
