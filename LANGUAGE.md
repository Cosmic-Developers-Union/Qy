# Qy 语言草稿

Qy 是一个宿主于 Python 的小型符号语言。

在当前 form 与数据类型完成后，核心语言视为冻结。后续扩展应发生在库、宿主算子、分析器或运行时策略中，不再新增核心语义。

## 源码

Qy 源码是一组 form。

- `abc` 是 symbol。
- `"abc"` 也是 symbol，内容为 `abc`。
- `(f a b)` 是 tuple form，并按调用求值。
- `'x` 是 `(quote x)` 的语法糖。
- `;` 开始一行注释。

Qy 当前没有独立的 string value。文本由 `Symbol` 表示。

## 值

核心值：

- `nil`
- `true`、`false`
- 整数和浮点数
- symbol
- tuple
- list
- dict
- set
- 算子
- continuation
- effect definition
- host object reference

tuple 是不可变符号序列，同时也是源码层面的调用 form。list、dict、set 是运行时数据值，用于宿主互操作和普通数据处理。

## 求值

求值规则：

- symbol 在当前词法环境中解析。
- 内建字面量解析为 `nil`、布尔值、整数或浮点数。
- 非空 tuple 先求值第一个元素作为算子，然后应用算子。
- `quote` 返回参数本身，不求值。
- body 按顺序求值所有 form，并返回最后一个值。

普通求值中，未解析 symbol 是错误。部分文本/数据边界算子会把未解析 symbol 保留为 symbol 值，例如 `print`、`str-*`、`py`、`tuple`、`list`、`dict`、`set`。

如果 symbol 名称已经被绑定，它会解析为该绑定。需要强制得到 symbol 值时使用 `quote`，例如 `'py`。

## 作用域

核心作用域 form：

- `(let ((name expr) ...) body...)`
- `(lambda (arg ...) body...)`
- `(defun name (arg ...) body...)`
- `(component name (arg ...) body...)`
- `(module name body...)`
- `(from module import name as alias ...)`

Qy 使用词法作用域。函数、组件、宏会捕获其定义环境。

## 数据算子

构造：

- `(tuple value...)`
- `(list value...)`
- `(dict key value...)`
- `(set value...)`

谓词：

- `(tuple? value)`
- `(list? value)`
- `(dict? value)`
- `(set? value)`

访问：

- `(len value)`
- `(get collection key [default])`
- `(has? collection key)`

`car`、`cdr`、`cons` 支持 tuple 和 list。

## Effect

核心 effect form：

- `(defeffect name)`
- `(defeffect name :resumable false)`
- `(perform effect arg)`
- `(handle expr ((effect (arg k) body...) ...))`
- `(resume k value)`

`perform` 执行 effect。`handle` 捕获匹配的 effect。`resume` 继续一个可恢复 effect 的 continuation。

不可恢复 effect 可以像 catch 一样被处理；但尝试恢复它会抛出 `QY_EFFECT_ERROR`。

内建不可恢复 effect：

- `python-error`
- `assert-failed`

## Assert

`(assert condition [message])` 是 debug 算子。

如果 `condition` 为 truthy，返回该 condition 值。如果为 falsey，执行 `assert-failed`，参数为 `message` 或 `assertion failed`。

`assert-failed` 不可恢复。

## Async

Qy 运行在 Python async runtime 上。

异步算子：

- `(spawn expr)`
- `(await expr...)`
- `(parallel expr...)`
- `(cache expr)`
- `(py source :name value ...)`

`parallel` 会把多个失败保留为 `QY_AGGREGATE_ERROR`。

## Python 互操作

`py` 嵌入 Python 代码，并将其编译为 async function。

Qy 到 Python：

- `nil` -> `None`
- bool/int/float -> 同名 Python 值
- `Symbol` -> `str`
- tuple -> `tuple`
- list -> `list`
- dict -> `dict`
- set -> `set`
- Qy callable -> async Python callable
- host object reference -> 被包装的 Python 对象

Python 到 Qy：

- `None` -> `nil`
- bool/int/float -> 同名 Qy 值
- `str` -> `Symbol`
- `tuple` -> tuple
- `list` -> list
- `dict` -> dict
- `set` -> set
- 其他 Python 对象 -> `HostObjectRef`

`py` 内部的 Python 异常会变为不可恢复 effect：`python-error`。

## 错误

所有 Qy 错误都派生自 `QyError`。

错误携带：

- 稳定错误码
- 消息
- source span
- Qy trace frame
- cause
- metadata

原生 Python 异常在宿主边界处包装。用户可见输出默认简洁；debug 输出可以包含 Python traceback。

## 静态分析

分析器刻意保持轻量。

它检查语法、未解析 symbol、基础 arity、基础类型预期和已声明 effect。它目前不提供完整 effect type system，也不证明所有 effect 都被处理。
