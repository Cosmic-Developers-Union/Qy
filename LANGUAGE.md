# Qy Language

Qy 是 Python 实现的 like-Lisp 语言，核心目标是 algebraic effects + register VM。Python 是宿主，不是语言语义本体。

## Pipeline

```text
source -> raw AST -> surface dialect -> macro expand -> HIR -> MIR -> LIR -> bytecode -> register VM
```

- `source`：文本。
- `raw AST`：reader 输出的原始 syntax datum，只负责字符到 `symbol` / `chain`。
- `surface dialect`：reader 后、macro expand 前的表层方言规约层；不属于语言内核语义。
- `macro expand`：macro 展开，输入/输出仍是 syntax datum。
- `HIR`：高层语义 IR，解析 binding、operator signature、effect signature、module/macro 语义。
- `MIR`：CFG / virtual register IR，表达控制流、tail call、effect control flow。
- `LIR`：低层 register VM IR，完成 register layout、opcode lowering、host-call lowering、effect frame lowering。
- `bytecode`：register VM 指令序列，不重新理解 HIR/MIR 语义。
- `register VM`：唯一执行器。Qy 不保留可选 runtime backend；旧 IR VM / evaluator 只能作为迁移期待删除代码存在，不能作为语义来源。

## Data Model

- Syntax datum 只有两类：`symbol` 与 `chain`。
- `chain` 是不可变对象；`cons` / quasiquote / macro 改写必须构造新 chain，不能原地修改旧 chain。
- Everything is symbol：源码中的名字、数字拼写、字符串拼写、算子名，进入 syntax datum 时都是 symbol 或 chain。
- Runtime value 存在于 symbol-space/env 中，由 `number`、`string`、`object` 构成。
- `number` 与 `string` 是特殊 object。
- Host value 是一等 runtime value，Qy 可以直接操作；host/project 可以在实例化 Qy 时提供 pre-symbol-space，把任意 host value/operator 预先放进 symbol-space-chain。
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
- 裸 `,` 与 `,@` 永远保留普通 symbol，因此 `(define , 10)`、`(, 1 2)`、`(1 ,x)` 在普通上下文中仍是合法独立结构。
- `define`、`let`、`lambda`、`defun`、`macro` 等 binding/parameter 位置不做 surface dialect expansion，以保证这些 spelling 仍可被绑定。
- surface dialect 规则必须可静态描述，供 analyzer、LSP、formatter、source map 与 expansion trace 使用。
- Qy 源码内暂不支持用户自定义 reader macro；宿主嵌入未来可以通过 Qy 实例配置 surface dialect。

## Symbol Space

- Qy 没有 `setq`。
- `define` 在当前 symbol-space 构建一次性绑定；只检查当前 symbol-space 是否已有该 symbol，不检查 parent。
- `define` 会保护当前 symbol-space 内已绑定的 symbol，但可以 shadow 外层 symbol-space 中的任意 symbol，包括核心算子名、stdlib 名、pre-symbol-space 名、宿主注入名。
- **pre-symbol-space** 是 Qy 实例化时提供的外层/初始符号空间，不是语言内核。默认实现可以把传统符号预定义在这里，例如数字 spelling `1` 解析为 runtime `number(1)`。
- pre-symbol-space 可以是惰性的：不需要真的注册全部数字符号，但语义上这些符号被视为已经在该空间中定义。
- **宿主注入**（host injection）只是向某个明确的 symbol-space 注入 host value/operator。被注入的名字只在该 symbol-space 内不可重定义，子 symbol-space 可用 `define` 或 `let` shadow。
- `let` 构建新的局部 symbol-space，可以绑定任意 symbol，包括外层已有 symbol、核心算子名、宿主注入名。
- `module`、函数调用 frame、macro 定义环境都按 symbol-space 模型理解，只是生命周期、导出规则和 compile-time/runtime 可见性不同。
- 外部宿主可以通过注入 symbol-space 来注入 object(host value) 与 operator。
- 因为 symbol 不可在同一 symbol-space 内重绑定，HIR 可以把确定的 symbol ref 解析为稳定 binding/value；这是后续优化基础。

## Lookup

求值一个 symbol 时：

1. 在当前 symbol-space 链中查找 binding。
2. 找到则返回对应 runtime value。
3. 未找到时，进入 Qy 实例的 pre-symbol-space / default resolver。默认实现通常在这里把数字 spelling 解析为 `number`，把字符串 spelling 解析为 `string`，也可以由嵌入方提供项目自己的预定义符号。
4. 仍无法解析则是 unresolved symbol error。

宏展开阶段操作 syntax datum；runtime lookup 不应污染 macro namespace。macro 的 definition-site binding、hygiene、capture 必须由 compile-time symbol-space 明确建模。

## Core Operators

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

`+`、`-` 等算术纯算子不属于最小语言核；它们来自显式 stdlib、显式 host 注入或 operator namespace，不得通过默认宿主空间隐式出现。

## Operator Semantics

- `quote`：返回参数 syntax datum。
- `atom`：判断是否非 chain/pair。
- `eq`：遵循 Lisp eq 语义；symbol 按符号身份，chain/object 按 identity。
- `car` / `cdr` / `cons`：核心 chain 操作。
- `cond`：条件分支。
- `pipeline`：begin/end；串行求值，返回最后一个表达式。
- `parallel`：parallel-map 风格的 order-insensitive 求值组；允许 VM 并行求值，但不要求并行；支持 effect。
- `all`：barrier continuation；全部分支完成后恢复 parent continuation。
- `race`：first-resume wins；最先恢复 parent continuation 的分支决定结果。
- `defun` / `lambda` / `apply`：函数定义、匿名函数、动态调用。`defun` 是 `(define name (lambda ...))` 的语义糖；服从不可重绑定规则，同一 symbol-space 不可重复 `defun` 同名函数。
- `macro`：compile-time syntax datum -> syntax datum 改写。
- `quasiquote` / `unquote` / `unquote-splicing`：宏构造 syntax datum 的配套机制；default surface dialect 支持 `,x` 与 `,@x` 拼写。
- `gensym` / `capture`：hygiene 与 intentional capture 机制。
- `defeffect` / `perform` / `handle` / `resume`：代数效应定义、触发、处理、恢复。`defeffect` 走 `define` 语义，同一 symbol-space 内不可重复声明同名 effect。
- `pipeline`、`parallel`、`all`、`race` 是 HIR 独立节点（`PipelineExpr`、`ParallelExpr`、`AllExpr`、`RaceExpr`），不是普通 `CallExpr`；lowering 必须特殊处理，不能通过 operator dispatch 求值。
- `module` / `from` / `import` / `exports`：模块 symbol-space 与导入导出。

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

- stdlib 可以扩展命名空间与 host interop。语言内核没有宿主环境；Qy 实例可以配置 pre-symbol-space，默认实现也可以为数字、字符串等传统符号提供惰性预定义。
- analyzer/lowering/runtime 必须共享 operator metadata，不能各自发明语义。
- bytecode compiler 不能重新理解 HIR/MIR；低层语义 lowering 必须经由 LIR。
- register VM 是唯一执行目标；不得新增或保留可选 runtime backend。IR VM / legacy evaluator 只能作为迁移期删除对象。
