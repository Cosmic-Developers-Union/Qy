# Qy Operators

Qy 采用 s-expression 作为语法，提供一套核心内建（core built-in）和标准内建（standard built-in）操作符，支持用户定义的库函数和宿主能力。

Qy 支持 `受限read macro` 和 `macro` 两种方式的语法扩展，前者在 surface dialect 层面提供便利的语法糖，后者在 core built-in 层面提供强大的 compile-time syntax transformation 能力。

## 类型系统

- symbol: 符号, 唯一类型.
- chain: 链表, 由 cons 构造, 以 nil 结尾。空 `'()` 即 nil。
- nil: Qy 自身的 nil；同时表示空 chain `'()`，并在条件语义中为 false。
- t: Qy 自身的真值对象；不是 Python `True` 的别名。

## Runtime value, 运行时值.

Qy 执行器的 runtime value 由符号求值或者通过算子构造。runtime value 是 Qy 语义对象；Python value 只能作为当前实现或宿主互操作对象进入系统，不能反过来定义 Qy 的值模型。

### 值类型

- number: 数值, 默认由 int(无限精), float(IEEE 754 双精), complex(实部虚部均为 float), 有理数(分子分母均为 int) 四种类型构成。
- char: 字符。
- string: 字符串。

### Host references, 宿主引用

- host reference: 指向宿主对象的 Qy runtime value；宿主对象可以来自 Python、Go 或其他适配层，但其宿主表示不是 Qy 语义本体。
- Python profile 可以显式暴露 `True`、`False`、`None` 等 Python value reference；它们不是 Qy 的 `t` / `nil`。

### 引用/容器类型

#### List-like family types, 列表类类型.

- list: 可变列表。
- tuple: 不可变列表。
- set: 集合。
- `list[...]`: 受限列表类型。这是为了优化和 mop 运行时监控而设计的类型.
- `tuple[...]`: 受限元组类型。
- `set[...]`: 受限集合类型。

#### Dict-like family types, 字典类类型.

- dict: 字典。
- struct: 结构体. 例如 Go 语言中的 struct, Rust 语言中的 struct, C 语言中的 struct 都属于 struct 类型。
- object: 对象.

### Stream types, 流类型.

- stream: 流；按方向分为 input stream、output stream、bidirectional stream；按 element 类型分为 byte stream 与 char stream。

> Note: `read` 只从 stream 产出 syntax datum；它不直接产出任意 runtime value。

## 受限 read macro

- `'`: `quote` 的语法糖.
- `\``: `quasiquote` 的语法糖.
- `,`: `unquote` 的语法糖.
- `,@`: `unquote-splicing` 的语法糖.

## Lisp-like family operators

- quote: 返回 syntax datum，不求值。
- atom: 判断值是否不是非空 chain；因此 `symbol` 与 `nil` 都是 atom。
- eq: 按 identity 比较两个值；不承担 number/string value equality 或结构相等。
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

- if: 条件分支；支持 `(if ... () elif ... () else ())`；面向广义真假判断时可建立在 `truthy` 之上。
- for: 类似 Python 的 for 循环；支持 `(for var in iterable body)` 和 `(for (var1 var2 ...) in iterable body)` 两种形式。
- while: 类似 Python 的 while 循环；支持 `(while condition body)` 形式。

## 判断扩展算子, 由 standard profile 提供, 默认 build-in.

- truthy: 复杂真值判断算子；按其自身规则判断各种意义上的真值，并返回 `t` / `nil`。

## 类型扩展算子, 由 standard profile 提供, 默认 build-in.

### 数值算子

- `+`: 可由 standard profile 预装的数值加法；不是 core built-in。
- `-`: 可由 standard profile 预装的数值减法；不是 core built-in。
- `*`: 可由 standard profile 预装的数值乘法；不是 core built-in。
- `/`: 可由 standard profile 预装的数值除法；不是 core built-in。

### IO 算子

- `io`: 由 standard profile 注入的 host capability object；承载宿主 I/O 能力，供 Qy 库继续组合。
- `echo`: 基于 `io` 的标准便利算子；值为 `nil`，side-effect 是将参数输出到 stdout。

### 数据结构算子

- `chain`: 构造 chain 数据结构。

## Stdlib Operators, 标准库算子, 非 core built-in.

- `qy.num::*`: 数值库组；承载 number equality、比较、派生数值操作。
- `qy.str::*`: 字符(串)组；操作 runtime `string`，不操作 syntax `symbol`。

## Reification

- `read`: `stream -> syntax datum`。
- `eval`: `syntax datum + symbol-space-chain -> runtime value`。
- `reify`: `runtime value + target context -> syntax datum`；默认应以“再次求值后得到等价值”为目标，而不是默认承诺 identity round-trip。
- host reference 可以显式实现 `reify`；若无法自行决定，可 `perform` 对应 effect 交给外部 handler。

## Custom Operators

- 用户自定义算子应声明可供 analyzer / LSP 使用的元数据，例如参数数量、参数求值方式、参数类型、返回类型、effect、compile-time / runtime-meta 属性等。
