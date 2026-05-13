# Qy

Qy is a symbolic Lisp-like language implemented in Python.

## Compilation Pipeline

The public pipeline is intentionally explicit:

```text
source
  -> ast
  -> expand
  -> HIR
  -> MIR
  -> LIR
  -> bytecode
  -> register VM
```

For the Python API, the corresponding entry points are `Qy.read(...)`, `Qy.macroexpand_source(...)`, `Qy.lower(...)`, `Qy.lower_mir(...)`, `Qy.compile_bytecode(...)`, and `RegisterVirtualMachine(...)`.

`Qy.evaluate_source(...)` still defaults to the IR backend because it is the most complete runtime. `Qy(backend="bytecode")` is available, but the bytecode backend is still experimental and does not yet cover the full language surface, especially modules, effects, and several advanced operators.

Macro expansion denies compile-time effects by default through `MacroExpansionOptions(effect_policy="deny")`. This keeps expansion deterministic unless a caller explicitly opts into a looser policy.

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
qy examples/validation/00_host_arithmetic.qy
qy run examples/validation/00_host_arithmetic.qy
uv run python examples/run_validation.py
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
qy fmt examples/validation/00_host_arithmetic.qy
qy ast examples/validation/00_host_arithmetic.qy
qy check examples/validation/00_host_arithmetic.qy
```

Import standard operators with aliases:

```lisp
(from qy.str import str-upper as upper)
(upper "hello")
```

Print values without rebinding anything:

```lisp
(print "hello" (+ 1 2))
(echo "done")
```

String operators work on text symbols and return symbolic values:

```lisp
(str-upper "hello")
(str-concat "qy" "lang")
(str-split "a,b,c" ",")
(str-join "," '(a b c))
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

Run the pipeline explicitly:

```python
from qy import Qy

qy = Qy()
expansion = qy.macroexpand_source("(+ 1 2)")
program = qy.lower(expansion.forms)
mir = qy.lower_mir(program)
bytecode = qy.compile_bytecode(program)

assert mir.ok
assert qy.evaluate_bytecode(bytecode) == 3
```

Embed a qy instance and register application operators:

```python
from qy import Qy
from qy import Symbol
from qy.evaluator import PureOperator
from qy.stdlib import StandardModule
from qy.stdlib import register_module

qy = Qy()

@qy.register_pure("double")
def double(value):
    return value * 2

assert qy.evaluate_source("(double 21)") == 42

register_module(StandardModule("app.math", {Symbol("triple"): PureOperator("triple", lambda x: x * 3)}))
qy.evaluate_source("(from app.math import triple as t)")
assert qy.evaluate_source("(t 14)") == 42
```

## Operator Kinds

Qy currently has three operator kinds:

- pure operators: evaluate all arguments, then apply
- evaluation operators: receive unevaluated arguments and control evaluation order
- syntax operators: receive the whole syntax tree

Built-ins:

- pure: `atom`, `eq`, `car`, `cdr`, `cons`, `+`, `-`, `*`, `/`
- evaluation: `quote`, `cond`, `let`, `print`, `echo`, `str-*`
- syntax: `defun`, `from`

Example:

```lisp
(defun square (x)
  (* x x))

(square 12)
```
