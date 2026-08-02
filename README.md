# Qy

Qy is a symbolic Lisp-like language implemented in Python, with algebraic
effects as the core control abstraction and a register VM as the sole
execution target. The Python implementation is the host, not the language
semantics itself.

## Compilation Pipeline

The language contract is centered on a single explicit pipeline:

```text
source -> raw AST -> surface dialect -> macro expand -> HIR -> MIR -> LIR -> bytecode -> register VM
```

The canonical entry points are:

- **Source-to-bytecode (single-shot)**: `qy.build.pipeline.compile_source_to_bytecode`
  (the only sanctioned front-to-back path).
- **Per-stage artifacts**: `compile_source_to_kind(source, kind)` where
  `kind ∈ {"core-ast", "hir", "mir", "lir", "bytecode"}`.
- **CLI debugging**: `qy ast`, `qy expand`, `qy hir`, `qy mir`, `qy lir`,
  `qy bytecode`, `qy run`.
- **Public API**: `Qy` / `AsyncQy` (`qy.runtime`) for full evaluation,
  `RegisterVirtualMachine` (`qy.vm.instance.machine`) for bytecode execution.

`Qy.evaluate_source(...)` remains available as the standard convenience
entry for full evaluation. Backend selection is **not** part of the model:
register VM is the unique execution target.

The removed single-stage helpers — `Qy.macroexpand_source`,
`Qy.lower`, `Qy.lower_mir`, `Qy.compile_bytecode`,
`Qy.evaluate_bytecode`, `Qy.evaluate_ir`, `Qy.evaluate_ir_source`,
`qy.ir_vm.*`, `qy.evaluator`, `Qy(backend=...)` — are no longer exposed
and should not be reintroduced. See `docs/pipeline.md` §"稳定 API 与删除对象"
for the canonical removal list.

Macro expansion denies compile-time effects by default through
`MacroExpansionOptions(effect_policy="deny")`. This keeps expansion
deterministic unless a caller explicitly opts into a looser policy.

The current core is intentionally small:

- reader: qy source → symbolic forms (`qy.frontend.reader`).
- surface dialect: deterministic spelling normalization such as `'x` and
  quasiquote unquote sugar (`qy.frontend.surface`).
- CST parser: trivia-preserving concrete syntax tree (`qy.frontend.cst`).
- HIR / MIR / LIR / bytecode: independent pipeline stages
  (`qy.ir.*`, `qy.backend.vm.*`).
- analyzer: diagnostics and lightweight type checks (`qy.analysis`).
- formatter: locked qy source formatting (`qy.tools.fmt`).
- CLI: AST, macro expansion, HIR, MIR, LIR, bytecode, and execution views
  (`qy.cli`).
- LSP: diagnostics, completion, hover, and formatting over pygls
  (`qy.tools.lsp`).

## Usage

Install optional command line tools:

```shell
pip install 'QyLang[cli]'
```

Evaluate a file (explicit subcommand form is recommended; the implicit
`qy FILE` shortcut is dead code in current typer, see `qy/cli/__init__.py`):

```shell
qy run examples/validation/00_host_arithmetic.qy
uv run python examples/run_validation.py
```

Start the interactive interpreter:

```shell
qy repl
```

The REPL keeps one `Qy` instance alive and supports `.help`, `.env`,
`.ast`, `.fmt`, `.check`, and `.exit`.

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

Use the Python API:

```python
from qy import Qy
from qy import Symbol

qy = Qy()
assert qy.evaluate_source("(+ 1 2)") == 3
```

Compile through the canonical pipeline:

```python
from qy import Qy
from qy.build.pipeline import compile_source_to_bytecode

qy = Qy()
result = compile_source_to_bytecode("(+ 1 2)", qy.session)
assert result.ok
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

register_module(
    StandardModule(
        "app.math",
        {Symbol("triple"): PureOperator("triple", lambda x: x * 3)},
    )
)
qy.evaluate_source("(from app.math import triple as t)")
assert qy.evaluate_source("(t 14)") == 42
```

## Operator Kinds

Qy uses operator metadata to describe evaluation behavior. The minimal core
remains centered on syntax, chain, binding, control, ordering/join,
function, macro, effect, and module forms; additional helpers live in
stdlib or explicit host-injected namespaces. The five operator dispatch
classes (`PureOperator` / `ScopeOperator` / `ControlOperator` /
`EffectOperator` / `MetaOperator`) are still exposed for backward
compatibility but are not the primary extension path — new core semantics
must reach MIR / LIR / bytecode / VM, not this legacy dispatch.

Example:

```lisp
(defun square (x)
  (* x x))

(square 12)
```