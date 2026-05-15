# Qy TODO

本文件只描述**当前事实**和**下一步工作**；历史批次放入 `report.md`。  
最近一次基线验证（2026-05-16）：

- `uv run python -m pytest -q`：345 passed
- `uv run ty check .`：passed
- `uv run ruff check .`：passed
- `uv run python examples/run_validation.py`：10 / 10 passed
- `uv run python -m qy test.qy tests/qy`：4 / 4 passed

## 0. 不可漂移的契约

- Qy 是 Python 实现的 like-Lisp；核心目标是 algebraic effects + register VM。
- 唯一管线：`source -> raw AST -> surface dialect -> macro expand -> HIR -> MIR -> LIR -> bytecode -> register VM`。
- syntax datum 只有 `symbol` 与不可变 `chain`。
- runtime value 由 `number`、`string`、`object` 构成；`number` / `string` 是特殊 object；host value 是一等 runtime value。
- symbol 求值沿 symbol-space-chain 查找。
- `pre-symbol-space-chain` 不是语言设计目标，但它是标准实现起点；reader、analyzer、LSP、lowering、runtime 都必须围绕同一个 `Qy` 实例读取同一份初始链事实。
- 同一 symbol-space 不可重绑定。`define` 只检查当前空间；`let` 创建新空间，可绑定任何 symbol；`defun = define + lambda`；`defeffect` 服从 define-once。
- 核心 form：
  - `quote`
  - `atom eq car cdr cons`
  - `define let cond`
  - `pipeline parallel all race`
  - `defun lambda apply`
  - `macro quasiquote unquote unquote-splicing gensym capture`
  - `defeffect perform handle resume`
  - `module from import exports`
- `pipeline` 串行；`parallel` 只表示“允许并行”，并且支持 effect；`all` 是 barrier continuation；`race` 是 first-resume-wins。
- 不实现 unrestricted reader macro。默认 surface dialect 只提供可静态描述的 `'x`、quasiquote 内 `,x` / `,@x`。
- register VM 是唯一 runtime backend；任何第二执行路径都只能是删除对象。
- 新增算子前先判断能否由 Qy 自身实现；能自举的能力优先写成 Qy library。

## 1. 当前判定

### 已完成

- register VM 已成为唯一公开执行路径；`qy.ir_vm/` 与 `python_codegen.py` 已删除。
- `raw AST -> surface dialect -> macroexpand -> HIR -> MIR -> LIR -> bytecode -> VM` 主链已存在。
- `pipeline` / `parallel` / `all` / `race` / `apply` / effect 已进入 HIR、MIR、VM 主路径。
- macro 已具备 namespace、hygiene、trace、source map 的基础实现。
- CLI 已能查看 `ast` / `expand` / `hir` / `mir` / `lir` / `bytecode`。
- qytest 初版已落地：`test.qy` + `tests/qy/` + Python 集成测试。
- `evaluator.py` 已从主求值路径退出，体积降到约 450 行。

### 部分完成

- **pre-symbol-space-chain**：已有实例级 `literal_resolver`，但还不是“有序初始链”的完整模型。
- **LIR**：已有线性化与 register layout rewrite，但仍接近“扁平 MIR + bytecode opcode”。
- **macro**：展开已独立，compile-time facade 已有形状，但 module scope、capability、LSP 消费链路未闭合。
- **operator metadata**：已拆出 core / stdlib / legacy signature，但 analyzer、lowering、runtime 还没有完全由同一模型驱动。
- **qytest**：普通 Qy runner 已能跑，但仍依赖过渡 stdlib；精确的 public command 形态尚未作为真实入口验收。
- **examples**：已重写一批 validation，但仍有样例验证的是当前过渡实现，不是最终语言面。

### 已确认漂移

1. 当前实现仍把初始环境近似成“root scope + literal resolver”，还不能表达多个初始链节点及其相对位置。  
   这会让 standard profile、项目注入空间、字面量空间的 shadow 规则无法被统一建模。
2. runtime `string` 还未落地；当前 `"hello"` 仍报 unresolved symbol。
3. 语言核、standard profile、optional stdlib 仍未正式拆层；当前 `qy.core` / 默认环境还没有说明“哪些是核心，哪些只是默认 profile 预装”。
4. `eq` 契约需要再次核对：文档写 Lisp identity 语义，当前 number 路径仍带有 value-equality 实现痕迹。
5. LSP 仍直接使用 `standard_environment()`，没有跟随具体 `Qy` 实例，也没有消费 macro trace/source map。
6. `docs/language-core-audit.md` 仍需要持续跟踪 root shadow / `pre-symbol-space-chain` 的最终实现是否与文档一致。
7. benchmark baseline 仍保留旧 phase 名 `ir`，与当前 `hir_lower` / `mir_lower` / `lir_lower` 分段不一致。
8. qytest 的 Python 测试只覆盖 Typer runner；`python -m qy test.qy tests/qy` 可用，但 exact shell 入口 `qy test.qy tests/qy` 在当前环境仍未形成可靠验收。

## 2. P0：先把语言面闭合

### P0-1. pre-symbol-space-chain / lookup / define

- 把当前 resolver fallback 收口为标准实现的正式起点模型：
  - `Qy` 实例拥有可读的 `pre-symbol-space-chain`；
  - 链节点、节点顺序、lazy segment、可写 head 都要能表达；
  - reader、analyzer、LSP、lowering、runtime 读取同一份实例事实；
  - 不再依赖脱离实例的默认全局 literal 解析。
- 明确 profile 对 number / string spelling 的规则：
  - 某个 symbol 能否在当前层 `define`，只由它是否已存在于当前 head space 决定；
  - 若 `1` 只存在于链的后续节点，当前 head 可自然 shadow；若当前 head 已含 `1`，同层 `define` 必须失败；
  - 字符串 spelling 必须解析为 runtime `string`，而不是 unresolved symbol。
- 把 `define` / `defun` / `defeffect` / module import/export 全部统一到 current-space-only define-once。
- 加回归测试：同层重复绑定、子层 shadow、host 注入名、数字 spelling、字符串 spelling、analyzer/lowering/runtime 三方一致。

**完成标准**：同一段源码在 analyzer、lowering、runtime 对 binding 的判断完全一致；同一 profile 在所有阶段呈现同一条初始链。

### P0-2. 语言核 / standard profile / stdlib 边界

- 固定三层边界：
  - 语言核：不可替代的 core form；
  - standard profile：默认 `Qy()` 是否预装 arithmetic 等常用能力；
  - optional stdlib / host capability：显式引入的扩展能力。
- `+` 等 arithmetic 可以由 standard profile 预装，但不能因此写回语言核。
- Python container、legacy async helper、host interop 不得因为默认 profile 便利性而伪装成核心语义。
- 以 `docs/stdlib-operators.md` 为工作草案，先落地：
  - `qy.num`：最小 host primitive + 可由 Qy 自举的派生库；
  - runtime `string` 后再设计 `qy.str`，停止扩展旧 `str-*`。
- `operator_signature.py` 继续收口：
  - core 只保留真实核心 form；
  - stdlib / compat 明确分层；
  - metadata 至少统一 arity、argument policy、return type、effect、tail transparency。
- 默认 `Qy()`、CLI `operators`、analyzer、lowering、stdlib loader 必须看到同一个 profile 事实。

**完成标准**：语言核文档、standard profile、可选 stdlib 三层边界清楚；给定同一 profile，默认可见符号集合、CLI、静态分析完全一致。

### P0-3. macro 完成

- 完成 compile-time symbol-space：
  - definition-site binding；
  - module macro import/export；
  - capability / effect policy；
  - hygiene + `capture`；
  - trace / source map 接入 diagnostics 与 LSP。
- 保持 surface dialect 可枚举、静态、无 runtime 依赖；若继续增长，从 `reader.py` 拆出独立模块。
- 给 macro、quasiquote、splice、capture、module import 增加正向与负向 qytest。

**完成标准**：macro 不再依赖“运行时环境顺手可用”的偶然行为，LSP 能解释展开来源。

### P0-4. 语义审计收口

- 明确 `eq` 对 `number` / `string` 的正式语义，并统一代码、测试、`LANGUAGE.md`、`docs/stdlib-operators.md`。
- 模块表面只保留 `module/from/import/exports` 一套模型；清掉残余 `imports` 兼容路径和文档残影。
- `quote`、syntax datum、runtime value、`apply` 边界继续保持清晰，不允许旧 helper 把三者混用。

## 3. P1：把编译器边界做实

### P1-1. LIR 变成真正低层 IR

- MIR 只负责 CFG、virtual register、tail position。
- LIR 接管：
  - instruction selection；
  - physical register layout / allocation；
  - effect frame layout；
  - host-call ABI lowering；
  - block layout / rerank；
  - jump fixup；
  - peephole / copy cleanup；
  - debug span / trace injection。
- bytecode compiler 只消费最终 LIR，不再承担高层决策。

**完成标准**：`LIR -> bytecode` 不再接近结构复制；每类 rewrite 都能指出唯一归属层。

### P1-2. continuation / effect / virtual stack

- 把 effect frame、handler frame、resume token、parent continuation 显式建模到 LIR/bytecode。
- 固定 `parallel` / `all` / `race` 在 effect 下的 continuation 合流规则。
- 继续推进虚拟栈：
  - 自尾递归；
  - 互递归；
  - effect 边界下 tail call；
  - 禁止 Python call stack 成为语义基础。

**完成标准**：effect + tail call + ordering/join 组合可从 LIR/bytecode 直接解释，并有系统测试。

### P1-3. 删除 legacy

- `evaluator.py` 只允许继续缩小，不允许新增语义。
- `eval_runtime.py` 继续降级为兼容 facade。
- legacy `PureOperator` / `ScopeOperator` / `ControlOperator` / `EffectOperator` / `MetaOperator` 最终只允许作为 host adapter。
- 把 stdlib、module loader、测试逐步迁到正式 metadata + VM 路径。

**完成标准**：新增核心语义时无需同时改 evaluator 与 VM 两套实现。

## 4. P1：qytest 成熟化

- 固定 public 目标：`qy test.qy tests/`；`pytest` 与 qytest 长期共存。
- qytest 继续保持“runner 用 Qy 写，宿主只给最小 capability”：
  - 文件读取；
  - 列目录；
  - 路径判断；
  - CLI args；
  - 其他 DSL、assertion、reporting 优先用 Qy 自举。
- 迁移更多行为测试：
  - lookup / `pre-symbol-space-chain` / define / let；
  - runtime string；
  - macro hygiene；
  - `pipeline` / `parallel` / `all` / `race`；
  - effect；
  - module；
  - 错误路径。
- 增加真实 CLI 入口验收，不只测 Typer runner。
- 逐步移除 qytest 对过渡符号 `append`、`print`、默认 `+` 的隐式依赖，或明确把它们放入显式测试环境。

**完成标准**：一批核心语言契约由 qytest 自己验收，且命令行真实入口稳定。

## 5. P2：文档、测试、复杂度

### P2-1. 文档修正

- 以 `LANGUAGE.md` 为唯一语言真源；`docs/*`、`AGENTS.md`、`CLAUDE.md` 只复述，不另起定义。
- 持续核对：
  - `docs/language-core-audit.md` 中的 root shadow / `pre-symbol-space-chain` 结论；
  - `report.md` 中不再适用的完成宣告不得回流成当前事实。
- examples 必须说明验证的是哪条目标契约；只验证历史实现的样例删除。

### P2-2. benchmark / CI

- benchmark 只保留 register VM 维度。
- 重建 baseline，统一 phase：`source / macroexpand / hir_lower / mir_lower / lir_lower / bytecode_compile / bytecode_vm`。
- 覆盖 workload：
  - tail recursion；
  - effect-heavy；
  - module-heavy；
  - macro-heavy；
  - qytest runner。
- 先做趋势记录，再决定硬阈值与 CI gate。

### P2-3. 复杂度治理

当前冻结增长的文件：

- `qy/lowering.py`
- `qy/analyzer.py`
- `qy/register_vm.py`
- `qy/mir.py`
- `qy/macroexpand.py`
- `qy/macro_hygiene.py`
- `qy/reader.py`
- `qy/evaluator.py`

规则：

- 触碰这些文件，先确认能否拆职责，再新增分支。
- `evaluator.py` 只能减，不准加。
- 新模块必须对应明确边界，不能只是把旧复杂度搬家。
- 每批 `report.md` 必须记录：
  - 新增 / 删除文件；
  - 复杂度变化；
  - 仍未删除的 legacy 面；
  - 验证命令。

## 6. 当前删除清单

- 已删除：`qy.ir_vm/`、`python_codegen.py`。
- 待删除或降级：
  - `evaluator.py` 中剩余语义；
  - `eval_runtime.py` 兼容面；
  - legacy operator dispatch 对 core semantics 的承担；
  - 旧 `str-*`；
  - `imports` 残影；
  - 只验证过渡实现的 examples/tests。

## 7. 批次要求

- 每批只推进一个主题：`symbol-space`、`stdlib`、`macro`、`LIR`、`VM/effect`、`qytest`、`docs` 任选其一。
- 每批结束后更新 `report.md`，至少包含：
  - 本批目标；
  - 修改范围；
  - 已完成；
  - 未完成 / 风险；
  - 删除了什么；
  - 验证命令。
- 行为变更必须同步检查：
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
