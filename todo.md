# Qy TODO

本文件是当前推进工作的权威任务清单。`report.md` 只记录已完成批次；如果 `LANGUAGE.md`、`CLAUDE.md`、`AGENTS.md`、`docs/*` 与本文件冲突，优先修正文档一致性。

当前验证基线：

- `uv run python -m pytest -q`：356 passed
- `uv run ty check`：passed
- `uv run ruff check .`：passed

## 语言契约

Qy 是 Python 实现的 like-Lisp，核心是 algebraic effects + register VM。Python 是宿主，不是语言语义本体。

目标管线固定为：

```text
source -> raw AST -> surface dialect -> macro expand -> HIR -> MIR -> LIR -> bytecode -> register VM
```

不可变约束：

- Syntax datum 只有 `symbol` 与 `chain`。
- `chain` 是不可变对象；所有构造、拼接、macro 改写必须返回新 chain。
- Everything is symbol：数字拼写、字符串拼写、名字、算子名进入 syntax datum 时都不是独立 primitive syntax type。
- Runtime value 存在于 symbol-space/env 中，由 `number`、`string`、`object` 构成。
- `number` 与 `string` 是特殊 object；host value 是一等 runtime value。
- pre-symbol-space 取决于 Qy 实例化；语言内核没有宿主环境，但默认 Qy 实例可以惰性预定义数字、字符串等传统符号。
- host value/operator 可以通过实例 pre-symbol-space、显式注入或显式 import 进入 symbol-space-chain。
- `quote` 返回 syntax datum，不触发 runtime lookup。
- 同一 symbol-space 内不可重绑定。
- `define` 只检查当前 symbol-space；允许 shadow parent symbol-space 中的任意 symbol，包括核心、stdlib、host 注入名。
- pre-symbol-space / host 注入的 object/operator 视为其所在 symbol-space 的已有绑定；同一空间内不能被 `define` 覆盖，但子空间可以 shadow。
- `define` 是一次性绑定，不是 `set`。
- `let` 创建新的局部 symbol-space，可以 shadow 任意外层 symbol，包括核心算子名与 host 注入名。
- `defun` 等价于 `(define name (lambda ...))` 的语义糖，必须服从不可重绑定。
- `defeffect` 走 `define` 语义，同一 symbol-space 内不可重复定义。
- `pipeline`、`parallel`、`all`、`race` 是 HIR 独立节点，不是普通 operator call。
- `spawn`、`await`、`component` 不属于语言核心；`component` 后续只能作为库层组合算子回归。
- register VM 是唯一执行器；移除除 register VM 之外的 runtime backend，不保留 backend 选择。

核心算子集合：

| 类别 | 算子 |
| --- | --- |
| syntax | `quote` |
| chain | `atom` `eq` `car` `cdr` `cons` |
| binding | `define` `let` |
| control | `cond` |
| ordering/join | `pipeline` `parallel` `all` `race` |
| function | `defun` `lambda` `apply` |
| macro | `macro` `quasiquote` `unquote` `unquote-splicing` `gensym` `capture` |
| effect | `defeffect` `perform` `handle` `resume` |
| module | `module` `from` `import` `exports` |

非核心但可作为 stdlib/host interop 存在：

- 算术：`+` `-` `*` `/` 等
- Python 容器：`list` `tuple` `dict` `set`，只能显式 import 或 host 注入
- string helper：`str-*`，只能显式 import
- async helper：历史 `spawn` / `await`，只能显式 legacy import
- Python interop：`py` / `py::*`，只能显式 import 或 host 注入

Surface dialect：

核心语言不实现 unrestricted reader macro；默认 Qy surface dialect 在 reader 后、macroexpand 前实现以下习惯拼写：

| sugar | form                   |
| ----- | ---------------------- |
| `'x`  | `(quote x)`            |
| `,x`  | `(unquote x)`          |
| `,@x` | `(unquote-splicing x)` |

`,` 与 `,@` 裸符号保留为普通 symbol；`,x` / `,@x` 只在 `quasiquote` 上下文展开。binding/parameter 位置不做 surface dialect expansion。

surface dialect 约束：

- 规则必须可枚举、可静态描述，供 analyzer、LSP、formatter、source map 与 expansion trace 使用。
- 规则不查 runtime symbol-space，不受 `define` / `let` / import 影响。
- 规则不执行 Qy runtime 代码，不允许 effect / IO。
- Qy 源码内暂不支持用户自定义 reader macro。
- 宿主嵌入未来可以在 Qy 实例化时选择或提供 surface dialect。

## 工作纪律

- 每个任务批次只处理一个主题，不混改 macro、MIR、VM、stdlib。
- 每个任务批次必须更新 `report.md`，写清：范围、完成、未完成、风险、验证。
- 每个行为变更必须同步检查 `LANGUAGE.md`、`CLAUDE.md`、`AGENTS.md`、`docs/pipeline.md`、`docs/language-core-audit.md`。
- 新语义必须落到明确阶段：surface dialect / macro expand / HIR / MIR / LIR / bytecode / VM。
- bytecode compiler 不允许重新理解 HIR/MIR；语义 lowering 必须经由 LIR。
- 新核心算子不得通过 legacy `PureOperator` / `ScopeOperator` / `ControlOperator` / `MetaOperator` 扩散。
- 超过 6k tokens 的文件冻结增长，只允许修 bug 或拆分；超过 8k tokens 的文件优先拆分。
- 不能新增绕过完整 pipeline 的执行路径。

## P0: 立即修正

### P0-0. 移除多 backend，register VM 唯一化

状态：`Qy` 与 CLI 已固定 register VM；`EvaluationBackend` / `Qy(backend=...)` 已移除。`qy.ir_vm` 仅保留内部迁移代码，顶层 public API 已下沉，待后续物理删除目录。

任务：

- 删除 `EvaluationBackend` 和 `Qy(backend=...)` 参数。
- `Qy.evaluate_*`、CLI `run`、examples runner 全部固定走 `source -> raw AST -> surface dialect -> macro expand -> HIR -> MIR -> LIR -> bytecode -> register VM`。
- 删除或下沉 `Qy.evaluate_ir*`、`qy.ir_vm.evaluate_ir*` 作为 public API；IR VM 代码进入删除队列，不再作为 reference runtime。
- 删除 `evaluate_source` / `evaluate_async` 等 legacy evaluator public path，或标记为内部迁移待删并停止导出。
- 更新 `__init__.py`，不再把 IR VM / evaluator backend 当稳定 API re-export。
- benchmark 只保留 register VM 维度；不再比较 IR backend 与 bytecode backend。
- tests 改名：`test_ir_vm.py` 不能作为语义验收；必要场景迁移到 register VM 测试。

验收：

- `Qy()` 无 backend 参数，默认且唯一使用 register VM。
- `rg "backend=|EvaluationBackend|evaluate_ir|IRVirtualMachine"` 只剩待删兼容文件、迁移注释或不存在。
- CLI `run` 与 `qy FILE` 只能走 register VM。
- `uv run python -m pytest -q`、`uv run ty check`、`uv run ruff check .` 通过。

### P0-1. 文档一致性收口

目标：所有面向代理和维护者的文档必须表达同一个语言与架构模型。

任务：

- 重写 `CLAUDE.md`：
  - 删除旧管线 `Source -> Reader -> Forms -> Lowering -> IR -> Evaluator -> Values`。
  - 删除 `async-first` 作为语言定位。
  - 删除把 `component`、`await` 当核心能力的描述。
  - 写入完整管线 `source -> raw AST -> surface dialect -> macro expand -> HIR -> MIR -> LIR -> bytecode -> register VM`。
  - 明确 register VM 是唯一执行器；IR VM / evaluator 是删除对象，不是 reference runtime。
- 更新 `AGENTS.md`：
  - 更新项目概览和重要文件路径：`qy/environment.py`、`qy/operators.py`、`qy/runtime_values.py`、`qy/continuation.py`、`qy/ir_vm/`、`qy/lir.py`、`qy/lir_lowering.py`、`qy/register_vm.py`。
  - 更新核心源码流向到完整 pipeline。
  - 删除过时 examples 路径，改为当前 validation/example 入口。
  - 加入：修改语言语义时必须同步 `LANGUAGE.md` 与 `todo.md`。
- 更新 `LANGUAGE.md`：
  - 明确 pre-symbol-space 是实例配置；默认可惰性预定义数字/字符串，但 Python host interop 不属于默认语言核心；`define` 只检查当前 symbol-space，允许 shadow parent。
  - 明确 `defun` 是 `define + lambda` 语义糖。
  - 明确 `defeffect` 走 `define` 语义。
  - 明确 `pipeline/parallel/all/race` 是 HIR 独立节点。
- 重写 `docs/language-core-audit.md`：
  - 删除已完成的旧阻塞描述。
  - 只保留当前真实偏差：多 backend 残留、`define` 仍按 parent 查重、默认环境预加载 host interop、旧 core 暴露、`component` 残留、`RuntimeMetaCallExpr`、legacy operator dispatch、Python codegen 绕过 MIR/LIR、effect continuation 未最终化。
- 更新 `docs/pipeline.md`：
  - 描述 debug CLI 输出：ast / expanded ast / HIR / MIR / LIR / bytecode。
  - 明确每层输入输出和禁止跨层解释。

验收：

- 文档中不再把 `component`、`spawn`、`await` 描述为核心。
- 文档中不再把 evaluator/IR VM 描述为执行路径或 reference backend。
- `LANGUAGE.md`、`CLAUDE.md`、`AGENTS.md`、`todo.md` 对核心算子集合一致。

### P0-2. symbol-space 与不可重绑定

目标：把语言最核心的 binding 语义落到 runtime、analyzer、lowering。

任务：

- 为 `Environment` 增加显式一次性绑定 API，例如 `define_once`。
- 当前 symbol-space 已存在 symbol 时，`define_once` 必须报错。
- pre-symbol-space、host 注入、core operator 注册、stdlib 注册只在其所在当前空间内是已有绑定；子空间允许 shadow。
- 默认数字/字符串 pre-symbol-space 需要显式建模或惰性建模；analyzer/LSP 必须能读取 Qy 实例的 pre-symbol-space 配置。
- `let` 创建子 symbol-space；子空间允许 shadow 外层任意 symbol。
- `defun` 使用 define 语义：不能覆盖同一空间已有 symbol。
- `defeffect` 使用 define 语义：不能重复声明同一空间 effect。
- `module` export/import 绑定需要明确是当前空间 define-once / import-once；不得检查 parent。
- analyzer 必须诊断同一 symbol-space 内重复 define。
- HIR binding 记录必须能表达 stable binding/value，为后续预查找优化服务。

验收：

- `(define x 1) (define x 2)` 报错。
- host 注入 `x` 到当前空间后，同一空间 `(define x 1)` 报错。
- 子空间 `(define x 1)` 与 `(let ((x 1)) ...)` 均可以 shadow 外层或 host 注入的 `x`。
- 默认 Qy 实例若把 `1` 预定义在当前/pre-symbol-space，则同一空间 `(define 1 10)` 报错；`let` 创建的空子空间中可以定义 `1` 并 shadow。
- `(defun f ...) (defun f ...)` 报错。
- `(defeffect ask) (defeffect ask)` 报错。

### P0-3. 核心算子表收口

目标：默认 core 与语言契约一致。

任务：

- 实现或接入核心 `define`。
- 从默认 core 移除 `spawn`、`await`。
- 从默认 core 移除 `component`，并删除相关 HIR/MIR/LSP/operator signature 测试残留。
- 从默认 core 移除 Python 容器 helper：`list`、`tuple`、`dict`、`set`。
- 从默认 core 移除 `str-*` 暴露；保留到显式 stdlib namespace。
- 从默认环境移除 `qy.py` / `py` / Python container prelude；host interop 只能显式 import 或显式注入。
- 保留 arithmetic 为 host/stdlib 注入，不把它写入最小语言核。
- 保留或实现默认 pre-symbol-space 对数字、字符串等传统符号的惰性预定义；这不是 host interop prelude。
- 更新 `operator_signature.py`、`operator_docs.py`、`semantics.py`、CLI `operators` 输出。

验收：

- 默认环境不能解析 `spawn`、`await`、`component`、`py`、`list`、`tuple`、`dict`、`set`、`str-*`。
- 核心算子列表与 `LANGUAGE.md` 完全一致。
- 需要兼容的旧算子只能通过显式 namespace 或 legacy module 引入。

### P0-4. HIR 节点重建

目标：核心语义不再伪装成普通 call/operator dispatch。

任务：

- 新增或确认 HIR 独立节点：
  - `DefineExpr`
  - `PipelineExpr`
  - `ParallelExpr`
  - `AllExpr`
  - `RaceExpr`
  - `ApplyExpr`
  - macro family：`QuasiquoteExpr` / `UnquoteExpr` / `GensymExpr` / `CaptureExpr`，或等价 compile-time 表示
- 删除 `ComponentExpr`。
- 删除或裁决 `RuntimeMetaCallExpr`；默认方向是删除，runtime eval 只能走显式 `eval`/`RuntimeEvalExpr`。
- `defun` lowering 成 define/function 语义，不再是独立可重绑定定义。
- `defeffect` lowering 成 define/effect 语义。
- analyzer、formatter、LSP、CLI HIR dump 同步。

验收：

- `(pipeline a b c)` 的 HIR 不是 `CallExpr("pipeline", ...)`。
- `(parallel ...)`、`(all ...)`、`(race ...)` 的 HIR 均为独立节点。
- repo 中不再有可执行路径依赖 `ComponentExpr`。

### P0-5. macro 系统完成

目标：macro 是 compile-time `symbol/chain -> symbol/chain`，不泄漏 runtime 语义。

任务：

- 拆分并稳定：
  - `macro_scope.py`：macro namespace、module macro import/export。
  - `macro_hygiene.py`：rename、definition-site binding、intentional capture。
  - `macro_trace.py`：expansion trace、source map、diagnostics chain。
  - `macroexpand.py`：只保留编排。
- hygiene syntax form set 必须包含新核心 form：`define`、`pipeline`、`parallel`、`all`、`race`、`apply`、`quasiquote`、`unquote`、`exports`。
- `quasiquote` / `unquote` / `gensym` / `capture` 语义落地。
- module macro 必须有 definition-site compile-time symbol-space。
- macro expansion trace 能定位原始 form 与展开 form。
- 明确 compile-time effect 策略：默认禁止 runtime effect；需要 compile-time effect 时必须显式建模。

验收：

- 导出 macro 可以引用定义模块内未导出的 compile-time helper。
- hygiene alias 不出现在普通 runtime `Environment.bindings()`。
- intentional capture 只能通过 `capture` 表达。
- macro 展开前后 source map 可用于诊断。

### P0-6. ordering/join/effect VM 语义

目标：`pipeline/parallel/all/race` 与 algebraic effects 在 VM 中形成统一控制模型。

任务：

- `pipeline`：顺序求值，返回最后一个表达式。
- `parallel`：允许并行的表达式组；无并行能力时可串行执行，但程序不得依赖子表达式 observable effect 顺序。
- `all`：barrier continuation，全部分支完成后恢复 parent continuation。
- `race`：first-resume-wins；winner 恢复 parent continuation，loser continuation 必须取消、失效或被标记为不可 resume。
- `perform`：捕获当前 continuation 并交给最近动态 handler。
- `resume`：明确 one-shot 还是 multi-shot；默认任务方向是 one-shot，避免 handler 多次恢复同一 VM frame。
- handler 内再次 `perform` 时，必须明确是否由当前 handler stack 继续处理。
- LIR 需要 effect frame lowering，不把 effect frame 临时塞在 register VM Python 对象里。

验收：

- `pipeline` 中 effect 顺序稳定。
- `parallel` 支持 effect，且没有并行实现时仍语义正确。
- `all` 等待所有分支后返回聚合结果。
- `race` 只允许一个分支恢复 parent continuation。
- 重复 resume 同一 one-shot continuation 报错。

## P1: 管线收口

### P1-1. MIR/LIR/bytecode 覆盖新 HIR

任务：

- `DefineExpr` lowering 到 define-once 指令。
- `PipelineExpr` lowering 到顺序 basic block 或线性序列。
- `ParallelExpr` / `AllExpr` / `RaceExpr` lowering 到显式 join/control-flow 表示。
- `ApplyExpr` lowering 到动态 call。
- macro family 在 expand 阶段消解，不应进入 runtime MIR，除非明确作为 syntax datum runtime value。
- LIR 从“线性化 bytecode opcode”升级到真正 low-level IR：
  - register layout
  - host-call lowering
  - effect frame lowering
  - continuation layout
  - branch target resolution

验收：

- bytecode compiler 仍只做 LIR -> bytecode 结构转换。
- register VM 不再需要重新理解 HIR 语义。

### P1-2. register VM 成为唯一主执行器

任务：

- 删除 `Qy.evaluate_ir*` 与 IR VM public API。
- 新功能只加到 HIR/MIR/LIR/bytecode/register VM。
- legacy evaluator 与 IR VM 不再被视为 backend；只作为待删除迁移代码。

验收：

- CLI `run` 与公共 `Qy.evaluate_source` 只能使用 register VM。
- 旧 IR VM 测试迁移或删除，不作为新语义验收。

### P1-3. legacy evaluator 退场

任务：

- 新代码不再从 `qy.evaluator` import runtime 类型。
- `evaluator.py` 只作为 compatibility facade。
- 删除或迁移：
  - `UserFunction`
  - legacy body evaluator helper
  - `ScopeOperator` / `ControlOperator` / `MetaOperator` runtime dispatch
  - stdlib 中依赖 legacy eager/raw evaluator 的实现
- operator metadata 接管 analyzer、lowering、runtime dispatch 的共同语义描述。

验收：

- `rg "from qy.evaluator"` 只剩 compatibility/test 明确场景。
- 新核心算子没有 legacy operator class 实例。

### P1-4. module/import/export 模型收口

任务：

- module 是 symbol-space，import/export 是 binding/export 规则，不是 evaluator side effect。
- `exports` 作为核心 module form 明确进入 HIR。
- `from` / `import` 与 define-once 一致：不能覆盖当前空间已有 symbol。
- provisional `source_modules.py` 与正式 module loader 合并或明确分层。
- module macro scope 与 runtime module scope 分离但可追踪。

验收：

- runtime import 与 macro import 不混用 namespace。
- import 覆盖已有 symbol 报错。
- module-local macro helper 可用但不泄漏 runtime export。

### P1-5. analyzer / LSP 静态能力

任务：

- analyzer 使用同一套 binding/symbol-space 模型。
- analyzer 基于不可重绑定做 stable lookup。
- 每个核心算子声明 signature、return type、effect、evaluation order。
- 自定义 operator 必须有注册规范：signature、effect、evaluation strategy、host ABI。
- LSP 展示 resolved binding、type、effect、macro expansion trace。

验收：

- 重复 define 在 analyzer 阶段报错。
- 未声明 effect 的 perform 在 analyzer 阶段报错。
- LSP 能区分 symbol syntax、runtime value、operator、effect。

## P2: stdlib / host interop

### P2-1. stdlib namespace 化

任务：

- `stdlib/core.py` 只注册最小核心和必要 host bootstrap。
- Python 容器 helper 移到 `py::list`、`py::tuple`、`py::dict`、`py::set` 或等价 namespace。
- string helper 移到 `str` namespace 或显式 stdlib module。
- async helper `spawn` / `await` 移到 legacy/host async module，默认不加载。
- operator docs 区分 core、stdlib、host interop、legacy。

验收：

- 默认 `qy.core` 不含非核心容器/string/async helper。
- 默认 prelude 不含 `qy.py`；host interop 不自动进入 symbol-space。
- 示例中显式 import 非核心能力。

### P2-2. Python codegen 重新定位

当前 `python_codegen.py` 从 HIR 直接生成 Python，可作为 prototype，但不是主 pipeline。

任务：

- 短期：CLI 与文档标注为 experimental。
- 中期：决定是否改为 MIR/LIR 输入。
- 不允许 Python codegen 重新定义 `eq`、`quote`、effect、let/body 求值语义。
- effect codegen 若保留，必须有明确 continuation/coroutine 模型。

验收：

- 文档不把当前 HIR codegen 描述为最终 AOT backend。
- codegen 测试标注支持子集和不支持语义。

### P2-3. examples 作为验证集

任务：

- examples 分层：
  - `validation/core`
  - `validation/macro`
  - `validation/effect`
  - `validation/module`
  - `validation/host`
  - `design/experimental`
- 每个 validation 示例都能通过自动 runner。
- 过时示例不得留在默认 examples 根目录误导用户。
- 示例必须遵守最新核心算子，不使用 `component` / 默认 `spawn` / 默认 `await`。

验收：

- `uv run python examples/run_validation.py` 通过。
- `uv run python -m pytest tests/test_examples_validation.py -q` 通过。

### P2-4. benchmark / CI gate

任务：

- benchmark 区分 front-end、macroexpand、HIR lowering、MIR lowering、LIR lowering、bytecode compile、VM execute。
- baseline 与 pipeline 阶段绑定，避免只测总耗时。
- CI gate 保留最大回归阈值，但报告阶段级回归。
- tail recursion、effect resume、parallel/all/race 需要独立 benchmark。

验收：

- `make bench` 生成阶段化结果。
- `make bench-check` 能指出具体回归阶段。

## P3: 删除清单

必须删除或降级为 legacy/compatibility 的对象：

- `ComponentExpr`
- `component` core operator
- 默认 core `spawn`
- 默认 core `await`
- 默认 core `list` / `tuple` / `dict` / `set`
- 默认 core `str-*`
- `RuntimeMetaCallExpr`，除非重新定义为明确 runtime eval feature
- legacy `UserFunction`，在 bytecode function value 完全接管后删除
- legacy operator class dispatch，转为 operator metadata + VM host-call ABI
- `source_modules.py` provisional runtime/module 混合逻辑，module system 稳定后合并或删除
- IR VM 全部 public backend API 与实现
- legacy evaluator public backend API

## 调试 CLI 目标

需要稳定以下命令，方便观察每一层：

- `qy ast FILE`：reader 输出 syntax datum。
- `qy expand FILE`：macroexpand 后 syntax datum。
- `qy hir FILE`：HIR dump。
- `qy mir FILE`：MIR CFG dump。
- `qy lir FILE`：LIR linear dump。
- `qy bytecode FILE`：bytecode dump。
- `qy run FILE`：默认 register VM 执行。

验收：

- 每个 dump 命令都能显示 source span 或 source map。
- 每个 dump 命令都不执行 runtime side effect，除非命令明确说明需要执行 compile-time macro。

## 默认验证命令

普通：

```shell
uv run python -m pytest -q
uv run ty check
uv run ruff check .
```

全量格式与类型：

```shell
make lint
```

macro：

```shell
uv run python -m pytest tests/test_eval_macro.py tests/test_macroexpand.py tests/test_module_import.py tests/test_analyzer_scope.py -q
```

MIR / LIR / bytecode / VM：

```shell
uv run python -m pytest tests/test_mir.py tests/test_lir.py tests/test_register_vm.py tests/test_runtime.py -q
```

examples：

```shell
uv run python examples/run_validation.py
uv run python -m pytest tests/test_examples_validation.py -q
```

性能：

```shell
make bench
make bench-check
```
