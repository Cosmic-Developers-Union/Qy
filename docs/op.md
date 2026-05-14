# Qy Operator / Form Model

本文档只描述当前语言核。旧的 `PureOperator` / `ScopeOperator` / `ControlOperator` / `EffectOperator` / `MetaOperator` 是 legacy runtime dispatch 分类，不再作为语言设计分类继续扩展。

## 核心原则

- syntax datum 只有 `symbol` / `chain`。
- `chain` 是不可变对象，任何构造/改写都必须产生新 chain。
- symbol 求值沿当前 symbol-space-chain 查找。
- `define` 只在当前 symbol-space 一次性绑定，可以 shadow parent。
- pre-symbol-space 由 Qy 实例化决定；语言内核没有宿主环境，但默认实例可以惰性预定义数字、字符串等传统符号。
- host value/operator 是 runtime value，可以通过实例 pre-symbol-space、显式注入或显式 import 进入 symbol-space-chain。
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

这些能力可以存在于 stdlib、legacy module 或 host injection，但不得作为默认语言核心：

- arithmetic：`+` `-` `*` `/`
- Python containers：`list` `tuple` `dict` `set`
- string helpers：`str-*`
- legacy async helpers：`spawn` `await`
- Python interop：`py` / `py::*`
- `component`：后续只能以库层组合算子回归

## 实现约束

- 核心 form 必须 lowering 为 HIR 独立节点或明确的核心 call 语义，再进入 MIR/LIR/bytecode/register VM。
- `pipeline`、`parallel`、`all`、`race` 不是普通 host operator。
- macro 只能在 expand 阶段改变 syntax datum；runtime 不能重新解释 macro。
- 新语义不得通过 legacy operator dispatch 扩展。
