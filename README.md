# Qy

Qy is a symbolic Lisp-like language implemented in Python.

The current core is intentionally small:

- reader: qy source -> symbolic forms
- tuple exchange: Python tuple forms with explicit `Symbol(...)`
- evaluator: simple symbolic evaluation
- CLI: file evaluation and interactive REPL
- LSP: syntax diagnostics over pygls

## Usage

Evaluate a file:

```shell
qy examples/codes/code001.qy
```

Start the interactive interpreter:

```shell
qy
```

Start the language server over stdio:

```shell
qy lsp
```

Use the Python API:

```python
from qy import Symbol
from qy import evaluate
from qy import evaluate_source

assert evaluate_source("(+ 1 2)") == 3
assert evaluate((Symbol("+"), 1, 2)) == 3
```

In Python tuple forms, normal Python values are literals. Use `Symbol(...)` when a tuple element is a qy symbol.

```python
from qy import Symbol
from qy import evaluate

evaluate((Symbol("+"), 1, 2))  # 3
evaluate(("+", 1, 2))          # error: "+" is a Python string literal
```

## Operator Kinds

Qy currently has three operator kinds:

- pure operators: evaluate all arguments, then apply
- evaluation operators: receive unevaluated arguments and control evaluation order
- syntax operators: receive the whole syntax tree

Built-ins:

- pure: `atom`, `eq`, `car`, `cdr`, `cons`, `+`, `-`, `*`, `/`
- evaluation: `quote`, `cond`
- syntax: `defun`

Example:

```lisp
(defun square (x)
  (* x x))

(square 12)
```
