# Qy Language

Qy 是 Python 实现的 like-Lisp 语言，核心目标是 algebraic effects + register VM。Python 是宿主，不是语言语义本体。

## Pipeline

```text
source -> raw AST -> surface dialect -> macro expand -> HIR -> MIR -> LIR -> bytecode -> register VM
```

- `source`：文本。
- `raw AST`：reader 输出的原始 syntax datum，只负责字符到 `symbol` / `chain`；不得提前引入 runtime value。
- `surface dialect`：reader 后、macro expand 前的表层方言规约层；不属于语言内核语义。
- `macro expand`：macro 展开，输入/输出仍是 syntax datum。
- `HIR`：高层语义 IR，解析 binding、operator signature、effect signature、module/macro 语义。
- `MIR`：CFG / virtual register IR，表达控制流、tail call、effect control flow。
- `LIR`：低层 register VM IR，完成 register layout、opcode lowering、host-call lowering、effect frame lowering。
- `bytecode`：register VM 指令序列，不重新理解 HIR/MIR 语义。
- `register VM`：唯一执行器。Qy 不保留可选 runtime backend；旧 IR VM / evaluator 只能作为迁移期待删除代码存在，不能作为语义来源。

## Data Model

- Syntax datum 只有两类：`symbol` 与 `chain`。
- 语法只有 S-expression；`form` 只是“一个 S-expression 单元”的叙述名：
  - 原子 form 是 `symbol`
  - 复合 form 是由 form 组成的 `chain`
- `quote`、`define`、`lambda`、`perform` 等只是后续阶段对某些 chain 的语义解释，不是 AST 的额外种类。
- `chain` 是不可变对象；`cons` / quasiquote / macro 改写必须构造新 chain，不能原地修改旧 chain。
- Everything is symbol：源码中的名字、数字拼写、字符串拼写、算子名，进入 syntax datum 时都是 symbol 或 chain。
- Runtime value 存在于 symbol-space/env 中；抽象上由 `number`、`string`、`object` 构成，`number` 与 `string` 是特殊 object。
- `nil` 与 `t` 是 Qy 自身对象。
- Runtime value 是 Qy 语义对象，Python value 只是当前实现或宿主互操作对象；两者不得混淆。一个 host reference 可以指向 Python、Go 或其他宿主对象，但宿主对象的本地表示不是 Qy 语义本体。
- Python profile 可以显式暴露 `True`、`False`、`None` 等 Python value reference；它们不等同于 `t` / `nil`。
- Host reference 是一等 runtime value，Qy 可以直接操作；host/project 可以在实例化 Qy 时提供 `pre-symbol-space-chain`，把任意 host reference/operator 放进初始查找链的指定位置。
- `quote` 返回 syntax datum，不触发 runtime lookup。

## Surface Dialect

语言内核不实现 unrestricted reader macro。`'x`、`,x`、`,@x` 在核心模型中都可以只是普通 symbol spelling。默认 Qy 实现为了 Lisp 使用习惯启用 default surface dialect，在 reader 之后、macro expand 之前做可枚举的符号拼写规约：

| sugar | form                   |
| ----- | ---------------------- |
| `'x`  | `(quote x)`            |
| `,x`  | `(unquote x)`          |
| `,@x` | `(unquote-splicing x)` |

- reader 本身保留 raw symbol：`read_raw("'x")` 是 symbol spelling，而不是 quote form。
- 默认 `read` / pipeline 会应用 default surface dialect。
- `,x` / `,@x` 只在 `quasiquote` 上下文内展开；脱离 `quasiquote` 时保留普通 symbol。
- `,@x` 属于默认 surface dialect 的支持范围；它展开为 core built-in `unquote-splicing`。
- 裸 `,` 与 `,@` 永远保留普通 symbol，因此 `(define , 10)`、`(, 1 2)`、`(1 ,x)` 在普通上下文中仍是合法独立结构。
- `define`、`let`、`lambda`、`defun`、`macro` 等 binding/parameter 位置不做 surface dialect expansion，以保证这些 spelling 仍可被绑定。
- surface dialect 规则必须可静态描述，供 analyzer、LSP、formatter、source map 与 expansion trace 使用。
- Qy 源码内暂不支持用户自定义 reader macro；宿主嵌入未来可以通过 Qy 实例配置 surface dialect。

## Symbol Space

- Qy 没有 `setq`。
- `define` 在当前 symbol-space 构建一次性绑定；只检查当前 symbol-space 是否已有该 symbol，不检查 parent。
- `define` 会保护当前 symbol-space 内已绑定的 symbol，但可以 shadow 链上后续 symbol-space 中的任意 symbol，包括核心算子名、stdlib 名、预置字面量名、宿主注入名。
- **pre-symbol-space-chain** 不是语言设计目标本身，但它是标准实现的起点。一个 `Qy` 实例先给出自己的初始 symbol-space-chain；reader、analyzer、LSP、lowering、runtime 都必须围绕这个同一实例工作。
- `pre-symbol-space-chain` 不是单个特殊空间，而是一段有序链。标准 profile、项目注入、字面量空间、stdlib 空间都可以是链上的不同节点；它们的相对位置决定 lookup 与 shadow 结果。
- 默认实现可以在链上放入传统符号空间，例如让数字 spelling `1` 解析为 runtime `number(1)`；这样的空间可以是惰性的，不需要真的注册全部数字 symbol。
- **宿主注入**（host injection）只是向链上的某个明确 symbol-space 放入 host reference/operator。被注入的名字只在那个空间内不可重定义；若当前 head 位于它之前，则 `define` 或 `let` 可以自然 shadow。
- `let` 构建新的局部 symbol-space，可以绑定任意 symbol，包括外层已有 symbol、核心算子名、宿主注入名。
- `symbol-space-chain` 只描述 lookup 可见性，不改变任何节点的本地 binding 集合。
- **fold** 把一个 chain 或某个 export view 当前可见的 binding 吸收到目标 symbol-space：fold 之后，这些 binding 对目标空间而言就是本地 binding，后续 `define` 必须按同层重复定义处理。
- `module` root 可以在构造时 fold profile chain；这样被吸收的名字不再只是“外层可见”，而是 module root 已有的本地 binding。
- `module`、函数调用 frame、macro 定义环境都按 symbol-space 模型理解，只是生命周期、导出规则和 compile-time/runtime 可见性不同。
- 外部宿主可以通过注入 symbol-space 来注入 object(host reference) 与 operator。
- 因为 symbol 不可在同一 symbol-space 内重绑定，HIR 可以把确定的 symbol ref 解析为稳定 binding/value；这是后续优化基础。

## Lookup

求值一个 symbol 时：

1. 在当前 symbol-space 链中查找 binding。
2. 找到则返回对应 runtime value。
3. 若局部 frame 已查尽，则继续沿该 `Qy` 实例提供的 `pre-symbol-space-chain` 顺序查找。默认 profile 可以在链上放入数字、字符串、stdlib 或项目自定义空间。
4. 仍无法解析则是 unresolved symbol error。

宏展开阶段操作 syntax datum；runtime lookup 不应污染 macro namespace。macro 的 definition-site binding、hygiene、capture 必须由 compile-time symbol-space 明确建模。

## Read, Eval, Reify

- `read`：`stream -> syntax datum`；不得越过 syntax/runtime 边界直接产出任意 runtime value。
- `eval`：`syntax datum + symbol-space-chain -> runtime value`。
- `reify`：`runtime value + target context -> syntax datum`；是 partial operation，不要求所有 value 都可 reify。
- 默认 `reify` 契约以“再次求值后得到等价值”为目标；若需要 identity round-trip，必须显式依赖 binding、handle 或其他上下文引用。
- host reference 可以显式实现 `reify`；若自身无法给出合适表示，可以 `perform` 一个 reify effect，交由外部 handler 决定是导出引用、构造表达式还是拒绝。

## Core Built-ins

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

`+`、`-` 等算术纯算子不属于最小语言核；它们可以来自显式 stdlib、显式 host 注入，或由标准 profile 预装进 `pre-symbol-space-chain`。默认 profile 是否加载它们属于标准实现策略，不改变语言核边界。

标准 profile 可以提供比语言核更便利的判断算子，例如 `truthy`。`cond` 的核心条件语义只把 `nil` 视为 false；`truthy` 负责按自身规则解释更复杂的广义真值，并返回 `t` / `nil`。这类复杂判断属于显式算子语义，不是全局宿主值自动转换规则。

## Operator Semantics

- `quote`：返回参数 syntax datum。
- `atom`：判断值是否不是非空 chain；因此 `symbol` 与 `nil` 都是 atom。
- `eq`：遵循 Lisp eq 语义；比较 Qy runtime identity，而不是 Python `id()` / `is`。number 值相等、string 值相等、结构相等请使用专用算子（`=`、`str=`、`equal`）。
- `car` / `cdr` / `cons`：核心 chain 操作。
- `cond`：条件分支。
- `truthy`：标准 profile 的复杂真值判断算子；用于构造更便利的 `if` 一类扩展控制算子，不改变 `cond` 的核心语义。
- `pipeline`：begin/end；串行求值，返回最后一个表达式。
- `parallel`：parallel-map 风格的 order-insensitive 求值组；允许 VM 并行求值，但不要求并行；支持 effect。
- `all`：barrier continuation；全部分支完成后恢复 parent continuation。
- `race`：first-resume wins；最先恢复 parent continuation 的分支决定结果。
- `defun` / `lambda` / `apply`：函数定义、匿名函数、动态调用。`defun` 是 `(define name (lambda ...))` 的语义糖；服从不可重绑定规则，同一 symbol-space 不可重复 `defun` 同名函数。
- `macro`：compile-time syntax datum -> syntax datum 改写。
- `quasiquote` / `unquote` / `unquote-splicing`：宏构造 syntax datum 的核心配套机制。
- `gensym` / `capture`：hygiene 与 intentional capture 机制。
- `defeffect` / `perform` / `handle` / `resume`：代数效应定义、触发、处理、恢复。`defeffect` 走 `define` 语义，同一 symbol-space 内不可重复声明同名 effect。
- `pipeline`、`parallel`、`all`、`race` 是 HIR 独立节点（`PipelineExpr`、`ParallelExpr`、`AllExpr`、`RaceExpr`），不是普通 `CallExpr`；lowering 必须特殊处理，不能通过 operator dispatch 求值。
- `module`：构造具名 symbol-space。
- `exports`：给模块的本地 binding 建立一个可对外 fold 的 export view。
- `from`：从另一个模块的 export view 选择 binding，并 fold 到当前 symbol-space；它改变当前空间的 local membership，不只是追加 lookup fallback。
- `import`：模块导入语法中的命名动作；若导入本地名已存在，冲突规则与同层 `define` 一致，除非显式 alias。

## Effects And Parallel

Qy 不使用 `spawn` / `await` 作为核心算子。

- 并发结构由 `parallel` 表达。
- 顺序结构由 `pipeline` 表达。
- 挂起点由 `perform` 表达。
- 恢复由 `resume` 表达。
- 调度策略由 `handle` 中的用户代码表达。
- `all` 与 `race` 定义 parent continuation 的聚合/恢复策略。

`parallel` 只表示“允许并行”，不要求实现必须并行。没有并行能力的 VM 可以串行执行 `parallel`，但程序不能依赖其子表达式的 observable effect 顺序；需要固定顺序时使用 `pipeline`。

`perform` 捕获当前 continuation 并交给最近的动态 handler。handler 可以立即 `resume`，也可以保存 continuation 并在 host callback、queue 或其他调度逻辑中稍后 `resume`。

## Architecture Rules

- stdlib 可以扩展命名空间与 host interop。语言内核没有宿主环境；Qy 实例可以配置 `pre-symbol-space-chain`，标准 profile 也可以把数字、字符串、`io` 这类 runtime model 或常用 stdlib 作为链段预装进去。
- 依赖 Python / Go 等宿主生态的能力，优先映射到明确的 Qy runtime model、host reference 或 module，再由 Qy 库在其上组合出便利算子；不要让宿主类型系统反向定义语言模型，也不要为每个宿主动作扩大 core built-in 面。
- chain 与 fold 必须分离建模：chain 只提供 lookup；fold 才会把 binding 纳入某个 symbol-space。本规则同时约束 module root 初始化与 `from`。
- 新增算子前必须先判断它是否能由 Qy 自身实现；可以由 Qy 组合出的能力应写成 Qy library，而不是新增 host operator。只有文件系统、进程参数、宿主对象桥接等不可由语言自身构造的能力，才应进入 host capability 层。
- analyzer/lowering/runtime 必须共享 operator metadata，不能各自发明语义。用户自定义算子若希望进入 analyzer / LSP 的静态世界，必须由创建者声明足够信息，例如 arity、argument policy、argument / return type、effect、compile-time / runtime-meta 属性。
- bytecode compiler 不能重新理解 HIR/MIR；低层语义 lowering 必须经由 LIR。
- register VM 是唯一执行目标；不得新增或保留可选 runtime backend。IR VM / legacy evaluator 只能作为迁移期删除对象。
