# Qy 语言草稿

Qy 是一个嵌入式、动态类型(强类型)、函数式、基于 effect 的 Lisp 方言，运行在 Python async runtime 上.

## 设计哲学

- 一切皆符号.
- 简单.

## 语法

Qy 语法基于 S-expression，使用前缀表示法。除此之外, 没有其他任何规则.

对于单个的文件, 支持多个 S-expression, 以及注释. 例如:

```qy
; 这是一个注释
(op ...)
(op ...)
```

## 词法

核心 reader 规则:

- `abc` 读为 symbol.
- `"abc"` 读为 symbol, 内容为 `abc`.
- `(f a b)` 读为 chain form.
- `(a . b)` 读为 dotted chain form.
- `'x` 读为 `(quote x)`.
- `tag"abc"` 读为 `(tag (quote "abc"))`.
- `tag"""abc"""` 读为 `(tag (quote """abc"""))`.
- `;` 开始一行注释.

## Execution Backend 执行后端

Qy 通过 python 完成`执行后端`的设计.

Qy 支持如下特性:

- REPL, 解释执行
- JIT and AOT 编译
- 编译为纯 Python 代码

## 求值模型

Qy 的求值模型基于 symbol space lookup 和默认求值。当对一个 symbol 进行求值时, Qy 首先会在 symbol space (env) 中查找该 symbol 的绑定. 如果找到了, 就返回绑定的值. 如果没有找到, 将会采用求职模型的默认求值规则进行求值. 默认求值规则如下:

- 基本尊重

## 值

核心值：

- symbol
- chain
- `true`、`false`、`none`
- 整数和浮点数
- list
- tuple
- dict
- set
- 算子
- continuation
- effect definition
- host object reference

Qy 源码只直接产生两类结构：symbol 和 chain。symbol 是符号；chain 是 `()`、`(a b c)`、`(a . b)` 这样的 Lisp 链。

`true`、`false`、`none` 是预定义 symbol，直接映射到 Python `True`、`False`、`None`。`nil` 是兼容别名，也映射到 Python `None`，但不等于空 chain `()`。

`none`、`nil`、`false` 和空 chain `()` 为 falsey，数字 `0` 为 truthy。

`'()` 是空 chain，不是 `none`，也不是 Python `list`。`'(a b c)` 是 proper chain，`'(a . b)` 是 dotted chain。

Python `list`、`tuple`、`dict`、`set` 是运行时数据值，由对应算子显式转换得到，用于宿主互操作和普通数据处理。它们和 chain 保持边界清晰。

## 求值

求值规则：

- symbol 在当前词法环境中解析。
- 内建 symbol `true`、`false`、`none` 解析为 Python 值。
- 数字符号解析为整数或浮点数。
- 非空 chain 先求值第一个元素作为算子，然后应用算子。
- `quote` 返回参数本身，不求值。
- body 按顺序求值所有 form，并返回最后一个值。

普通求值中，未解析 symbol 是错误。部分文本/数据边界算子会把未解析 symbol 保留为 symbol 值，例如 `print`、`str-*`、`py`、 `tuple`、`list`、`dict`、`set`。

如果 symbol 名称已经被绑定，它会解析为该绑定。需要强制得到 symbol 值时使用 `quote`，例如 `'py`。

## 数据算子

构造：

- `(cons head tail)` 构造 chain cell；`tail` 为 chain 时得到 proper chain，为其他值时得到 dotted chain。
- `(list value...)` 转换为 Python list；单参数为 chain 时展开 chain。
- `(tuple value...)` 转换为 Python tuple；单参数为 chain 时展开 chain。
- `(dict key value...)` 转换为 Python dict；单参数为 pair chain 时转为 dict。
- `(set value...)` 转换为 Python set；单参数为 chain 时展开 chain。

访问：

- `(car value)` 返回 chain/tuple/list 的第一个元素。
- `(cdr value)` 返回 chain/tuple/list 的剩余部分；对 dotted chain 返回 tail。
- `(len value)`
- `(get collection key [default])`
- `(has? collection key)`
- `(type value)` 返回类型名称；`(type '(1 2 3))` 返回 `chain`。

比较：

- `(== a b)` 使用 Python `==` 语义。
- `(is a b)` 使用 Python `is` identity 语义。
- `(eq a b)` 使用 Lisp 风格 eq；symbol 按名称比较，chain 按 identity 比较，`()` 只等于 `()`。

谓词：

- `(tuple? value)`
- `(list? value)`
- `(dict? value)`
- `(set? value)`

## 作用域

核心作用域 form：

- `(let ((name expr) ...) body...)`
- `(lambda (arg ...) body...)`
- `(defun name (arg ...) body...)`
- `(component name (arg ...) body...)`
- `(module name body...)`
- `(from module import name as alias ...)`

Qy 使用词法作用域。函数、组件、宏会捕获其定义环境。

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
