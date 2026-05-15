# Qy TODO

本文件只保留当前工作面；历史批次写入 `report.md`。  
最近一次基线验证：

- `uv run python -m pytest -q`：345 passed
- `uv run ty check .`：passed
- `uv run ruff check .`：passed

## 1. 不可漂移的语言契约

- Qy 是 Python 实现的 like-Lisp，语言核心是 algebraic effects + register VM。
- 固定管线：`source -> raw AST -> surface dialect -> macro expand -> HIR -> MIR -> LIR -> bytecode -> register VM`。
- syntax datum 只有 `symbol` 与不可变 `chain`。
- runtime value 由 `number`、`string`、`object` 构成；`number` / `string` 是特殊 object；host value 是一等 runtime value。
- symbol 求值沿 symbol-space-chain 查找。
- pre-symbol-space 不是语言设计目标本身，但它是标准实现的起点；reader、analyzer、LSP、lowering、runtime 都必须围绕同一个 `Qy` 实例及其 pre-symbol-space 工作。
- 同一 symbol-space 内不可重绑定。
- `define` 只检查当前 symbol-space；允许 shadow parent。`let` 创建新的局部 symbol-space，可绑定任意 symbol。
- `defun` 是 `define + lambda` 语义糖；`defeffect` 也服从 define-once。
- 核心 form：
  - `quote`
  - `atom eq car cdr cons`
  - `define let cond`
  - `pipeline parallel all race`
  - `defun lambda apply`
  - `macro quasiquote unquote unquote-splicing gensym capture`
  - `defeffect perform handle resume`
  - `module from import exports`
- `parallel` 只表示“允许并行”，不是强制并行；它支持 effect。`pipeline` 表示串行；`all` 是 barrier continuation；`race` 是 first-resume-wins。
- 不实现 unrestricted reader macro。默认实现只提供可静态描述的 surface dialect：`'x`、quasiquote 内的 `,x`、`,@x`。
- register VM 是唯一 runtime backend；任何新 backend、绕过 pipeline 的执行路径、以及重新把 evaluator/IR VM 当语义来源，均视为回退。

## 2. 当前进度判定

### 已完成

- register VM 已成为唯一公开执行路径；`qy.ir_vm/` 已删除。
- raw AST / surface dialect / macro expand / HIR / MIR / LIR / bytecode / VM 的主链已经存在。
- `chain` 已实现为不可变对象。
- `pipeline`、`parallel`、`all`、`race`、`apply`、effect HIR/MIR/VM 路径已有形状。
- macro namespace、hygiene、trace、source map 已拆出基础模块。
- CLI 已能查看 `ast` / `expand` / `hir` / `mir` / `lir` / `bytecode`。
- validation examples、Python 测试、类型检查、lint 当前均可通过。

### 正在完成

- macro 已从 evaluator 主路径中脱离，但 compile-time capability、module macro scope、LSP 消费 trace/source map 还未最终化。
- evaluator 已退成兼容层，但 legacy operator dispatch 仍然承载大量行为。
- MIR 已承担 CFG；LIR 仍只是“扁平 MIR + bytecode opcode”，还不是独立低层 IR。
- operator metadata 已存在，但尚未统一 analyzer / lowering / runtime dispatch。
- examples 已开始重写，但仍更多是在验证“当前实现”，不是完整验证“目标语言”。

### 已确认语义漂移 / 工程缺口

1. `define` 的 root scope 语义分裂已修复（2026-05-16）：  
   `lowering` / `analyzer` / runtime 对 `(define + 99)` 已统一为同层重绑定错误；子空间（如 `let`）仍允许 shadow parent。
2. pre-symbol-space 已显式建模（2026-05-16）：  
   `Environment` 支持实例级 `literal_resolver`，并在 child 环境继承；`analyzer` / `lowering` / `runtime` 可读取同一实例环境事实。未完成项：字符串 spelling 仍未默认映射为 runtime `string`。
3. 默认 core 与语言契约不一致：  
   `qy.core` 仍默认引入算术；文档却已把算术定义为非核心、需显式 stdlib/host 注入。
4. quasiquote 收口已完成（2026-05-16）：  
   `unquote-splicing` 现使用正式 `append` 语义，不再生成未定义 helper。
5. `apply` 语义收口已完成（2026-05-16）：  
   `(apply + (quote (1 2)))` 可按 runtime 参数序列工作，默认字面量 spelling 会在 apply 边界归一化。
6. module surface 双轨已移除（2026-05-16）：  
   `imports` block 已从语义路径移除，module 内统一使用 `from` form。
7. `LIR -> bytecode` 部分收口（2026-05-16）：  
   `LIR` 已新增 register layout 重写（虚拟寄存器压缩与布局归整），不再完全是 MIR 结构直拷贝。未完成项：effect frame layout / host-call ABI / block rerank / debug 注入仍待实现。
8. metadata / legacy 层持续收口（2026-05-16）：  
   `evaluator.py` 已删除一段不再走主 pipeline 的遗留 effect/assert 解释路径；`qy/` 内对 evaluator 的直接依赖已收敛到 `eval_runtime.py`。未完成项：legacy operator classes 仍作为兼容层存在。

## 3. P0: 先闭合语义

### P0-1. symbol-space / pre-symbol-space 一次定型

- 把 pre-symbol-space 建模为标准实现起点，而不是隐式 fallback：
  - `Qy` 实例拥有自己的起始 symbol-space；
  - reader、analyzer、LSP、lowering、runtime 都从该实例读取同一份 pre-symbol-space 事实；
  - 不允许再出现脱离实例的默认全局解析。
- 把当前 fallback resolver 收口成显式 pre-symbol-space 能力：
  - 支持实例级配置；
  - analyzer / LSP 可读取；
  - 默认实现如何处理 number / string spelling 要与文档一致。
- `define` / `defun` / `defeffect` / module import/export 全部统一到 current-space-only define-once。
- 加入回归测试：
  - 同层重复 `define` 失败；
  - 子空间 shadow parent 成功；
  - host 注入名在同层不可重定义、在子层可 shadow；
  - 顶层程序对 pre-symbol-space 的行为与文档完全一致。

**完成标准**：同一段源码在 analyzer、lowering、runtime 三处对 binding 的判断一致；不再出现“静态允许、VM 拒绝”的 root-scope 分裂。

### P0-2. 默认语言面收口

- 明确 `qy.core` 的最小导出集合；算术、string helper、Python 容器、legacy async helper 全部显式 namespace 化。
- 重新整理 `operator_signature.py`：
  - 只保留真实 core；
  - 为 `define`、`pipeline`、`parallel`、`all`、`race`、`apply`、quasiquote family、module family 补齐 signature；
  - signature 至少描述 arity、argument policy、return type、effect、tail transparency。
- analyzer、lowering、stdlib、CLI `operators` 必须读取同一 metadata 源。
- 新增 operator 必须先经过“是否可由 Qy 自身实现”的审查：
  - 可由 core + library 组合出的能力写成 Qy library；
  - 只有文件系统、进程参数、宿主对象桥接等不可下沉能力才进入 host capability 层；
  - 测试、容器 sugar、控制组合、reporting 一类能力默认不得先做成 host operator。

**完成标准**：默认 `Qy()` 的可见符号集合、`LANGUAGE.md`、`operators` 输出、静态分析结果一致。

### P0-3. macro / quasiquote / apply 收口

- 完成 `quasiquote` / `unquote` / `unquote-splicing` 的正式语义；删除 `qy-append` 这类悬空 helper。
- 明确 syntax datum 与 runtime value 的转换边界：
  - `quote` 只返回 syntax datum；
  - `apply` 需要明确接收何种 runtime chain / callable；
  - 不能靠偶然的 host callable 容忍错误类型。
- 完成 macro compile-time capability：
  - definition-site compile-time symbol-space；
  - module macro import/export；
  - hygiene + `capture`；
  - compile-time effect policy；
  - expansion trace / source map 给 diagnostics 与 LSP 使用。
- surface dialect 继续保持可枚举、静态、无 runtime 依赖；若继续增长，先从 `reader.py` 拆出独立模块。

**完成标准**：macro 系统能用自身定义验证例；quasiquote splice、`apply`、macro module import 都有正向和负向测试。

### P0-4. module surface 定稿

- 决定 public surface：
  - `import` 保持 `from` 结构关键字，不单独作为 form；
  - `imports` block 视为历史残留并已移除出语义路径。
- 只保留一种 public model；其余若保留，必须降为内部表示，不再出现在语言契约中。
- 统一 module runtime export、macro export、source module 预扫描、analyzer、lowering、VM 的 define-once 规则。

**完成标准**：`LANGUAGE.md`、reader、macroexpand、HIR、source module、analyzer、VM 只表达同一套模块语义。

## 4. P1: 把编译器边界做实

### P1-1. LIR 变成真正的低层 IR

- MIR 继续负责 CFG、控制流、virtual register、tail position。
- LIR 新增并承接：
  - instruction selection；
  - register layout / physical allocation；
  - effect frame layout；
  - host-call ABI lowering；
  - block layout / rerank；
  - jump fixup；
  - peephole / copy cleanup；
  - debug span / trace injection。
- bytecode compiler 只消费最终 LIR，不再承担任何高层决策。
- register VM 不再替编译器补高层语义；VM 只执行 bytecode。

**完成标准**：`LIR -> bytecode` 不再是一比一结构复制；能明确列出每个低层 rewrite 在哪一层完成。

### P1-2. continuation / effect VM 语义最终化

- 把 effect frame、handler frame、resume token、parent continuation 在 LIR/bytecode 中显式建模。
- 收口 `parallel` / `all` / `race` 在 effect 下的 continuation 合流规则。
- 继续推进虚拟栈：
  - 自尾递归、互递归、effect 边界下的 tail call 规则都要可说明；
  - 不再依赖 Python call stack 作为语义基础。

**完成标准**：effect + tail call + ordering/join 的组合有系统测试，VM 行为能从 LIR/bytecode 直接解释。

### P1-3. 删除遗留层

- `python_codegen.py` 已删除（2026-05-16）：当前目标只有 register VM。
- `evaluator.py` 继续缩成兼容 facade，禁止新增语义；能迁出的全部迁出。
- legacy `PureOperator` / `ScopeOperator` / `ControlOperator` / `EffectOperator` / `MetaOperator` 逐步降级为 host adapter，不再承载 core semantics。
- `eval_runtime.py`、文件模块加载、旧 stdlib 路径逐步切到正式 pipeline。

**完成标准**：新增核心语义时无需同时修改 evaluator + VM 两套实现；repo 中不再存在第二条事实上的执行路径。

## 5. P1: Qy 原生测试框架

### 目标

目标不是新增一个 `qy test` 子命令，而是先让普通 Qy 程序承担测试运行器职责：

```bash
qy test.qy tests/
```

`pytest` 与 qytest 长期共存：

- `pytest` 验证 Qy 执行器与编译器各层是否正确：reader、macroexpand、HIR/MIR/LIR、bytecode、VM、diagnostics、LSP、host bridge。
- `qy test.qy tests/` 验证语言从使用者角度呈现出的行为特征：binding、macro、effect、module、并发组合等。

### 设计原则

- qytest 自身优先用 Qy 实现，不把测试 DSL 直接做成 host operator。
- 宿主只补 Qy 无法自举的最小 capability，先按下列候选收敛：
  - 读取文本文件；
  - 列出目录；
  - 必要时的路径判断；
  - CLI 参数暴露给程序。
- 在真正写 `test.qy` 前，不预先新增高层测试 operator；`suite`、`test`、assertion、过滤、reporting 等若能由 Qy 写出，就必须由 Qy 写出。
- Qy 没有 `set`，`chain` 不可变，因此 suite / report 应优先建模为不可变数据。
- 失败优先建模为 effect，而不是依赖 Python exception 直通。
- 若测试文件发现、动态加载仍无法仅靠现有 module 语义完成，再单独论证是否需要一个新的最小 capability；不得先把整套 runner 做进 Python。

### 第一批迁移到 Qy 的测试

- quote / chain / `eq`
- `define` / `let` / shadow / root-space 行为
- `lambda` / `defun` / `apply`
- `pipeline` / `parallel` / `all` / `race`
- `defeffect` / `perform` / `handle` / `resume`
- macro hygiene / quasiquote
- module import/export 的正向路径

### 仍保留在 Python 的测试

- reader tokenization、span、surface dialect 原始 form
- analyzer/LSP diagnostics 的精确内容
- HIR/MIR/LIR/bytecode dump 与 verifier
- host injection、stdlib loader、CLI、性能基准

### 落地任务

- 新建 `tests/qy/` 作为 qytest 输入，不再把 `examples/validation/` 同时当示例和测试。
- 先写普通 Qy 程序 `test.qy`，目标执行形态固定为 `qy test.qy tests/`。
- 只实现最小 host capability module；其余 runner 逻辑由 Qy 自身实现。
- Python 侧只保留启动/集成验证，不把 qytest 逻辑反向搬回 pytest。
- 每次新增语言语义，至少判断是否需要：
  - Python unit test；
  - Qy behavior test；
  - validation example。

**完成标准**：至少一组核心语义验收由 Qy suite 自己完成，并纳入默认 CI；examples 回到“示例”，tests/qy 承担“验证”。（已完成：`test.qy` + `tests/qy/` + `tests/test_qytest_runner.py`）

## 6. P2: 文档、示例、复杂度治理

### P2-1. 文档与示例对齐

- `LANGUAGE.md` 是语言真源；`docs/*`、`AGENTS.md`、`CLAUDE.md` 只能复述，不得另起定义。
- validation examples 继续清理：
  - 不再把默认算术称作 host pre-space，除非实现最终确实如此；
  - 每个 example 必须标明验证的是目标语言哪一条契约；
  - 过时示例直接删，不保留兼容展示。
- `docs/language-core-audit.md` 只保留真实未闭合项，不再保存已完成历史。

### P2-2. 复杂度预算

当前需要冻结增长的文件：

- `qy/lowering.py`
- `qy/analyzer.py`
- `qy/register_vm.py`
- `qy/evaluator.py`
- `qy/mir.py`
- `qy/macroexpand.py`
- `qy/macro_hygiene.py`

规则：

- 触碰这些文件时，优先拆职责，再加新分支。
- `evaluator.py` 只允许减少语义，不允许新增语义。
- 新增模块必须对应明确边界，不允许把旧混乱平移到新文件。
- 每批次 `report.md` 必须写出：新增文件、删除文件、复杂度变化、仍未删除的 legacy 面。

### P2-3. benchmark / CI

- benchmark 只保留 register VM 维度。
- 建立历史基线与 regression gate：
  - parse / expand / lower / MIR / LIR / bytecode / VM 分段计时；
  - tail recursion、effect-heavy、module-heavy 三类 workload；
  - 至少先做趋势记录，再决定硬阈值。

## 7. 当前删除清单

- `python_codegen.py` 已删除。
- 继续削减 `evaluator.py` 与 `eval_runtime.py` 的真实语义承担。
- 清理 operator metadata 中不属于 core 的条目。
- 继续清理 legacy async、旧 compatibility tests 中不再被 public language 接受的路径（`imports` block 已移除）。
- 删除 examples 中只验证历史实现、无法说明目标语言契约的内容。

## 8. 批次工作要求

- 每次只推进一个主题：symbol-space、macro、module、LIR、VM、testing、docs 中择一。
- 每次提交后更新 `report.md`，至少写：
  - 本批目标
  - 修改范围
  - 已完成
  - 未完成 / 风险
  - 删除了什么
  - 验证命令
- 行为变更必须同步检查：
  - `LANGUAGE.md`
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
