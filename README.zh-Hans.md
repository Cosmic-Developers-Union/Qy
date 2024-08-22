# Qy

QyLang, 一个基于 Python 且由 Python 实现的 LISP 方言。

## 开发计划

- [ ] 添加 Qy 类作为解释器实例，qy 改为 qy 默认实例。
- [ ] 重构 symbol 求值规则与定义规则，兼容性的采用 Lisp-1, Lisp-2 的方式。

## 概览

Qy 的目标是一个典型的 LISP 方言。Qy 语言的语法和语义与 Scheme 和 Common Lisp 有很多相似之处，但区别任然很明显，Qy 语言的语法和语义更加简单，更加易于理解。

Qy 希望可以 Python 的语法和语义，以及 LISP 的简洁和易用性结合在一起，使得用户可以更加方便的使用 Python 的功能，同时也可以使用 LISP 的功能。

因此，使用 Qy 是容易的，你可以使用渐进式的方式学习 Qy 语言，你可以使用 Python 的方式来编写 Qy 语言，也可以使用 LISP 的方式来编写 Qy 语言。这都可以。

由于需要保持 Qy 与 Python 的 互操作性，因此，Qy 设计了两套语言体系：Qy 语言和中间语言。Qy 语言是一种类似于 LISP 的语言，而中间语言是特殊格式 Python 的语言（你可以直接在 Python 中写它，实际上，它就是 Python 语言）。

## 语法

### 字符串

字符串是由双引号括起来的字符序列。例如：

```lsp
(print "Hello World!")
```

这里与 Python 的求值方式不同，字符串中可以包含除了双引号之外的任何字符。因此，以下的表达是合法的：

```lsp
(print "
hello world! \n
")
```

## 中间语言

中间语言完全由 Python 的`tuple`构成，其类型符合`Tuple[symbol, int, float, str, bytes]`。

其中 symbol 为符号，int float str bytes 为中间语言原子类型。

一个典型的表达式由以下内容构成：

```python
s_expression = (operator, sybol, 1, 1.0, '1', b'1', s_expression)
```

对于中间语言求值问题，有两种区分，当操作符是一个算符或定义的函数时，所有符号将会被求值。

例如，对于

```lisp
(defn name (a '(b) '(c 1)) (add a b c))
(name 1 2 3)
```

显而易见，`a`、`b`、`c`都是符号，但是在求值时，`a`、`b`、`c`都会被求值。

## 内置算符

- quote
- atom
- eq
- car
- cdr
- cons
- cond
