# Qy Language

Qy 是 Python 实现的 like-Lisp 语言，核心目标是 algebraic effects + register VM。Python 是宿主，不是语言语义本体。

## Pipeline

```text
source -> ast -> expand -> HIR -> MIR -> LIR -> bytecode -> register VM
```

- `source`：文本。
- `ast`：reader 输出的 syntax datum。
- `expand`：macro 展开，输入/输出仍是 syntax datum。
- `HIR`：高层语义 IR，解析 binding、operator signature、effect signature、module/macro 语义。
- `MIR`：CFG / virtual register IR，表达控制流、tail call、effect control flow。
- `LIR`：低层 register VM IR，完成 register layout、opcode lowering、host-call lowering、effect frame lowering。
- `bytecode`：register VM 指令序列，不重新理解 HIR/MIR 语义。
- `register VM`：最终执行器。IR VM 只是过渡期 reference runtime。

## Data Model

- Syntax datum 只有两类：`symbol` 与 `chain`。
- Everything is symbol：源码中的名字、数字拼写、字符串拼写、算子名，进入 syntax datum 时都是 symbol 或 chain。
- Runtime value 存在于 symbol-space/env 中，由 `number`、`string`、`object` 构成。
- `number` 与 `string` 是特殊 object。
- Host value 是一等 runtime value，Qy 可以直接操作。
- `quote` 返回 syntax datum，不触发 runtime lookup。

## Symbol Space

- Qy 没有 `setq`。
- `define` 在当前 symbol-space 构建一次性绑定；如果当前 symbol-space 已存在该 symbol，则非法。
- `define` 会保护当前 symbol-space 内已绑定的 symbol。
- `let` 构建新的局部 symbol-space，可以绑定任意 symbol，包括外层已有 symbol、核心算子名、宿主注入名。
- `module`、函数调用 frame、macro 定义环境都按 symbol-space 模型理解，只是生命周期、导出规则和 compile-time/runtime 可见性不同。
- 外部宿主可以通过注入 symbol-space 来注入 object(host value) 与 operator。
- 因为 symbol 不可在同一 symbol-space 内重绑定，HIR 可以把确定的 symbol ref 解析为稳定 binding/value；这是后续优化基础。

## Lookup

求值一个 symbol 时：

1. 在当前 symbol-space 链中查找 binding。
2. 找到则返回对应 runtime value。
3. 未找到时，可由预空间/default resolver 按 symbol spelling 产生 `number`、`string` 或其他 host object。
4. 仍无法解析则是 unresolved symbol error。

宏展开阶段操作 syntax datum；runtime lookup 不应污染 macro namespace。macro 的 definition-site binding、hygiene、capture 必须由 compile-time symbol-space 明确建模。

## Core Operators

| 类别          | 算子                                              |
| ------------- | ------------------------------------------------- |
| syntax        | `quote`                                           |
| chain         | `atom` `eq` `car` `cdr` `cons`                    |
| binding       | `define` `let`                                    |
| control       | `cond`                                            |
| ordering/join | `pipeline` `parallel` `race` `all`                |
| function      | `defun` `lambda` `apply`                          |
| macro         | `macro` `quasiquote` `unquote` `gensym` `capture` |
| effect        | `defeffect` `perform` `handle` `resume`           |
| module        | `module` `from` `import` `exports`                |

`+`、`-` 等算术纯算子不属于最小语言核；它们来自宿主预空间、stdlib 或 operator namespace。

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
- `defun` / `lambda` / `apply`：函数定义、匿名函数、动态调用。
- `macro`：compile-time syntax datum -> syntax datum 改写。
- `quasiquote` / `unquote`：宏构造 syntax datum 的配套机制。
- `gensym` / `capture`：hygiene 与 intentional capture 机制。
- `defeffect` / `perform` / `handle` / `resume`：代数效应定义、触发、处理、恢复。
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

- stdlib 可以扩展 runtime 预空间、命名空间与 host interop，但不能反向定义语法核心。
- analyzer/lowering/runtime 必须共享 operator metadata，不能各自发明语义。
- bytecode compiler 不能重新理解 HIR/MIR；低层语义 lowering 必须经由 LIR。
- register VM 是最终执行目标；IR VM 只能作为 reference/compatibility layer。
