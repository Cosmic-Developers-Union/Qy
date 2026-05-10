# Qy

Qy is a symbolic Lisp-like language implemented in Python.

The current core is intentionally small:

- reader: qy source -> symbolic forms
- tuple exchange: Python tuple forms with explicit `Symbol(...)`
- analyzer: diagnostics and lightweight type checks
- evaluator: simple symbolic evaluation
- formatter: locked qy source formatting
- CLI: optional file evaluation, REPL, formatting, AST, and type checking
- LSP: optional diagnostics, completion, hover, and formatting over pygls

## Usage

Install optional command line tools:

```shell
pip install 'QyLang[cli]'
```

Evaluate a file:

```shell
qy examples/codes/code001.qy
qy run examples/codes/code001.qy
```

Start the interactive interpreter:

```shell
qy
qy repl
```

The REPL keeps one `Qy` instance alive and supports `.help`, `.env`, `.ast`, `.fmt`, `.check`, and `.exit`.

Install optional language-server support:

```shell
pip install 'QyLang[lsp]'
```

Start the language server over stdio:

```shell
qy lsp
```

Format, inspect, and type-check qy source:

```shell
qy fmt examples/codes/code001.qy
qy ast examples/codes/code001.qy
qy check examples/codes/code001.qy
```

Use the Python API:

```python
from qy import Qy
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

Embed a qy instance and register application operators:

```python
from qy import Qy

qy = Qy()

@qy.register_pure("double")
def double(value):
    return value * 2

assert qy.evaluate_source("(double 21)") == 42
```

## Operator Kinds

Qy currently has three operator kinds:

- pure operators: evaluate all arguments, then apply
- evaluation operators: receive unevaluated arguments and control evaluation order
- syntax operators: receive the whole syntax tree

Built-ins:

- pure: `atom`, `eq`, `car`, `cdr`, `cons`, `+`, `-`, `*`, `/`
- evaluation: `quote`, `cond`, `let`
- syntax: `defun`

Example:

```lisp
(defun square (x)
  (* x x))

(square 12)
```
