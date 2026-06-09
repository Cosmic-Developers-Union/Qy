# Qy

Qy is a symbolic Lisp-like language implemented in Python.

## Compilation Pipeline

The language contract is centered on a single explicit pipeline:

```text
source -> raw AST -> surface dialect -> macro expand -> HIR -> MIR -> LIR -> bytecode -> register VM
```

For the Python API, the corresponding entry points are `Qy.read(...)`, `Qy.macroexpand_source(...)`, `Qy.lower(...)`, `Qy.lower_mir(...)`, `Qy.compile_bytecode(...)`, and `RegisterVirtualMachine(...)`.

`Qy.evaluate_source(...)` remains available as a compatibility convenience, but register VM is the execution target and backend selection is not part of the model.

Macro expansion denies compile-time effects by default through `MacroExpansionOptions(effect_policy="deny")`. This keeps expansion deterministic unless a caller explicitly opts into a looser policy.

The current core is intentionally small:

- reader: qy source -> symbolic forms
- surface dialect: deterministic spelling normalization such as `'x` and quasiquote unquote sugar
- tuple exchange: Python tuple forms with explicit `Symbol(...)`
- analyzer: diagnostics and lightweight type checks
- formatter: locked qy source formatting
- CLI: AST, macro expansion, HIR, MIR, LIR, bytecode, and execution views
- LSP: diagnostics, completion, hover, and formatting over pygls

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
from qy import PureOperator
from qy import Symbol
from qy.std import StandardModule
from qy.std import register_module

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

Qy uses operator metadata to describe evaluation behavior. The minimal core remains centered on syntax, chain, binding, control, ordering/join, function, macro, effect, and module forms; additional helpers live in stdlib or explicit host-injected namespaces.

Example:

```lisp
(defun square (x)
  (* x x))

(square 12)
```
