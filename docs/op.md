# Qy Operator / Form Model

本文档只描述当前语言核。旧的 `PureOperator` / `ScopeOperator` / `ControlOperator` / `EffectOperator` / `MetaOperator` 是 legacy runtime dispatch 分类，不再作为语言设计分类继续扩展。

## 核心原则

- syntax datum 只有 `symbol` / `chain`。
- `chain` 是不可变对象，任何构造/改写都必须产生新 chain。
- symbol 求值沿当前 symbol-space-chain 查找。
- `define` 只在当前 symbol-space 一次性绑定，可以 shadow 链上后续节点。
- `pre-symbol-space-chain` 不是语言设计目标本身，但它是标准实现的实例起点；reader、analyzer、LSP、lowering、runtime 都围绕同一个 `Qy` 实例工作。
- `pre-symbol-space-chain` 是有序链，不是单个特殊空间；profile、字面量空间、stdlib 空间、宿主注入空间都可以占据链上的明确位置。
- host value/operator 是 runtime value，可以通过实例 `pre-symbol-space-chain`、显式注入或显式 import 进入 symbol-space-chain。
- chain 只决定 lookup；fold 才会把可见 binding 吸收到当前 symbol-space，并使其成为本地 binding。
- `from` 是受 `exports` 约束的选择性 fold，不是普通 lookup fallback。
- register VM 是唯一执行器。

## Surface Dialect

核心语言不实现 unrestricted reader macro。默认 Qy surface dialect 在 reader 后、macroexpand 前做可枚举的符号拼写规约。

| sugar | form                   |
| ----- | ---------------------- |
| `'x`  | `(quote x)`            |
| `,x`  | `(unquote x)`          |
| `,@x` | `(unquote-splicing x)` |

`,` 与 `,@` 裸符号保留为普通 symbol；`,x` / `,@x` 只在 `quasiquote` 上下文展开。binding/parameter 位置不做 surface dialect expansion。源码内用户自定义 reader macro 暂不进入核心。

## 核心 form

| 类别 | form |
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

## 非核心能力

这些能力可以存在于 stdlib、legacy module、host injection，或由标准 profile 预装，但不得因此成为语言核心：

- arithmetic：`+` `-` `*` `/`
- Python containers：`list` `tuple` `dict` `set`
- string helpers：`str-*`
- legacy async helpers：`spawn` `await`
- Python interop：`py` / `py::*`
- `component`：后续只能以库层组合算子回归

非核心算子的工作草案单独维护在 `docs/stdlib-operators.md`，不进入核心语言规范。

## 实现约束

- 核心 form 必须 lowering 为 HIR 独立节点或明确的核心 call 语义，再进入 MIR/LIR/bytecode/register VM。
- `pipeline`、`parallel`、`all`、`race` 不是普通 host operator。
- `module` 是具名 symbol-space；`exports` 是可被外部 fold 的 view；`from` 把被选中的 export binding 纳入当前 symbol-space。
- macro 只能在 expand 阶段改变 syntax datum；runtime 不能重新解释 macro。
- 新增 operator 前先判断能否由 Qy 自身实现；能写成 Qy library 的能力，不要下沉成 host operator。
- 新语义不得通过 legacy operator dispatch 扩展。
