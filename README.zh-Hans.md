# Qy

QyLang, 一个基于 Python 且由 Python 实现的 LISP 方言。

## 语法

语法由扩展的 S 表达式构成。

其中`空格`、`换行符`等非空白字符被用来作为分隔符使用。`(`和`)`被用来作为列表的标志符。

其中，表达式支持类似 Scheme Common Lisp 的`'(`的实现，但该语法不属于强制的语法定义，它可以替代。

在 Qy 中，一切列表项均为原子类型符号，这意味着，你可以定义一个如下的变量。

```qy
(set 1 (int 2))
(set 1 `2)
(print (eq 1 2))
(; it will print true)
```

由此，引出了一个较为反直觉的内容，字符串并不强制需要引号。

对于解释器而言，每一个符号都应该首先到符号查找对应的值，如果如果没有定义，符号才会尝试解析。

或者可以使用

## 中间语言

中间语言完全由 Python 的`tuple`构成，其类型符合`Tuple[symbol, int, float, str, bytes]`。

其中 symbol 为符号，int float str bytes 为中间语言原子类型。

一个典型的表达式由以下内容构成：

```python
s_expression = (operator, sybol, 1, 1.0, '1', b'1', s_expression)
```
