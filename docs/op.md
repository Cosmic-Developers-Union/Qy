# Qy Operators

Qy 采用 s-expression 作为语法，提供一套核心内建（core built-in）和标准内建（standard built-in）操作符，支持用户定义的库函数和宿主能力。

Qy 支持 `受限read macro` 和 `macro` 两种方式的语法扩展，前者在 surface dialect 层面提供便利的语法糖，后者在 core built-in 层面提供强大的 compile-time syntax transformation 能力。

## 受限 read macro

- `'`: `quote` 的语法糖.
- `\``: `quasiquote` 的语法糖.
- `,`: `unquote` 的语法糖.
- `,@`: `unquote-splicing` 的语法糖.

## Lisp-like family operators

- quote: 返回 syntax datum，不求值。
- atom: 判断值是否为 atom, 即是否是非空 chain 或者 symbol。
- eq: 测试两个atom是否相同。
- car: 取 chain 的首项。
- cdr: 取 chain 的余项。
- cons: 构造新的不可变 chain。
- cond: 条件分支。

## Lisp-like Extensions, lisp-like 扩展算子

- quasiquote: 构造 syntax datum；支持 unquote 和 unquote-splicing。
- unquote: 在 quasiquote 中插入求值结果。
- unquote-splicing: 在 quasiquote 中插入求值结果，并将结果作为 chain 的元素 splice 进来。

## 代数效应 Algebraic Effects and Handlers family operators

- `defeffect`: 定义 effect；服从当前 symbol-space 的 define-once。
- `perform`: 触发 effect，并捕获当前 continuation。
- `handle`: 安装 effect handler。
- `resume`: 恢复 continuation。

## Symbol-space family operators

- let: 构建新的局部 symbol-space；可绑定任意 symbol。
- define: 在当前 symbol-space 构建一次性绑定，并保护当前空间内已绑定的 symbol。
- module: 构造具名 symbol-space。
- from: 从模块 export view 选择 binding，并 fold 到当前 symbol-space。
- import: 指定从模块引入的名字或 alias。
- exports: 定义模块可被外部 fold 的 export view。

## Function family operators

- lambda: 构造匿名函数。
- defun: 定义函数；语义上等价于 `define + lambda`，服从不可重绑定。
- apply: 以运行时给出的参数序列调用函数。

## Macro family operators

- `macro`: 定义 compile-time syntax transformer。
- `capture`: 显式保留调用点 binding，跳过默认 hygiene rewrite。
- `gensym`: 生成 hygienic symbol。

## Concurrency family operators

- `parallel`: 标记一组表达式求值顺序无关，允许 VM 并行求值，但不要求并行；支持 effect。
- `pipeline`: 串行求值，返回最后一个结果。
- `race`: first-resume-wins；最先恢复 parent continuation 的分支获胜。
- `all`: barrier continuation；全部分支完成后恢复 parent continuation。

## 流程扩展算子, 由 standard profile 提供, 默认 build-in.

- if: 条件分支；支持 `(if ... () elif ... () else ())。
- for: 类似 Python 的 for 循环；支持 `(for var in iterable body)` 和 `(for (var1 var2 ...) in iterable body)` 两种形式。
- while: 类似 Python 的 while 循环；支持 `(while condition body)` 形式。
- defer: 注册一个 deferred effect handler；当当前 continuation 结束时，执行 handler body；支持 `(defer body)` 形式, 与`Go` 语言中的 defer 语义类似。

## 类型扩展算子, 由 standard profile 提供, 默认 build-in.

### 数值算子

- `+`: 可由 standard profile 预装的数值加法；不是 core built-in。
- `-`: 可由 standard profile 预装的数值减法；不是 core built-in。
- `*`: 可由 standard profile 预装的数值乘法；不是 core built-in。
- `/`: 可由 standard profile 预装的数值除法；不是 core built-in。

### IO 算子

- `echo`: 回显, 值为 `nil`, side-effect 是将参数输出到 stdout。

### 数据结构算子

- `chain`: 构造 chain 数据结构。

## Stdlib Operators, 标准库算子, 非 core built-in.

- `qy.num::*`: 数值库；承载 number equality、比较、派生数值操作。
- `qy.str::*`: 字符串库；操作 runtime `string`，不操作 syntax `symbol`。
