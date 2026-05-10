# Qy

Qy 是一个由 Python 实现的符号化 Lisp 方言。

当前核心保持很小：

- reader：qy 源码 -> 符号表达式
- tuple exchange：使用显式 `Symbol(...)` 的 Python tuple 交换格式
- evaluator：简单符号求值
- CLI：文件求值和交互式解释器
- LSP：基于 pygls 的语法诊断

## 使用

求值文件：

```shell
qy examples/codes/code001.qy
```

启动交互式解释器：

```shell
qy
```

通过 stdio 启动语言服务器：

```shell
qy lsp
```

Python API：

```python
from qy import Symbol
from qy import evaluate
from qy import evaluate_source

assert evaluate_source("(+ 1 2)") == 3
assert evaluate((Symbol("+"), 1, 2)) == 3
```

在 Python tuple 表达式中，普通 Python 值都是字面量。只有显式使用 `Symbol(...)` 才表示 qy 符号。

```python
from qy import Symbol
from qy import evaluate

evaluate((Symbol("+"), 1, 2))  # 3
evaluate(("+", 1, 2))          # error: "+" 是 Python 字符串字面量
```

## 算子类型

Qy 当前有三类算子：

- 纯算子：先求值所有参数，再调用算子
- 求值算子：接收未求值参数，自行控制求值顺序
- 语法树算子：接收完整语法树

内置算子：

- 纯算子：`atom`、`eq`、`car`、`cdr`、`cons`、`+`、`-`、`*`、`/`
- 求值算子：`quote`、`cond`
- 语法树算子：`defun`

示例：

```lisp
(defun square (x)
  (* x x))

(square 12)
```
