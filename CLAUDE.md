# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Qy is a symbolic Lisp-like language implemented in Python. It provides a minimal core with explicit symbol representation, a five-tier operator system with algebraic effects, and tooling support (REPL, formatter, type checker, LSP, VSCode extension).

## Commands

```bash
# Setup
uv sync --group dev                  # Install dev dependencies
uv sync --group cli --group lsp      # Also add CLI/LSP optional deps

# Testing
python -m unittest discover tests
python -m unittest tests.test_qy_evaluator                    # single file
python -m unittest tests.test_qy_evaluator.TestQyEvaluator.test_arithmetic_from_qy_source  # single test

# Linting & formatting
make lint          # ruff check, ruff format, ty check
make lint-fix      # auto-fix lint issues (includes --unsafe-fixes)

# Build
make build         # clean + uv build + twine check

# Run
qy run examples/basic.qy             # run a file
qy repl                              # interactive REPL
qy fmt <file>                        # format
qy ast <file>                        # show AST
qy check <file>                      # type check
```

## Architecture

The core pipeline: **Source → Reader → Forms → Evaluator → Results**

### Core modules (`qy/`)

- **`reader.py`** — Lark-based parser (LALR grammar). Converts Qy source to symbolic forms. Key types: `Symbol` (atomic identifier), `TupleForm` (nested s-expression), `Form` (union of both). Bidirectional: `read`/`read_one` parse source; `write`/`write_tuple` emit source.

- **`evaluator.py`** — Async-capable interpreter with **five operator kinds** controlling evaluation strategy:
  - `PureOperator` — evaluates all args first, then applies (e.g., `+`, `car`)
  - `ScopeOperator` — receives evaluated args plus the environment (e.g., `let`)
  - `ControlOperator` — receives unevaluated args and controls evaluation order (e.g., `quote`, `cond`). Aliased as `EvaluationOperator`.
  - `EffectOperator` — handles effect operations (e.g., `perform`, `handle`)
  - `MetaOperator` — receives raw unevaluated syntax (e.g., `defun`, `defmacro`, `from`). Aliased as `SyntaxOperator`.
  - `Environment` provides lexical scoping with shared cache. `UserFunction` and `ComponentDefinition` implement closures. All `evaluate_*` functions have `_async` variants.

- **`errors.py`** — Hierarchical error types rooted at `QyError`. Key subtypes: `QySyntaxError`, `EvaluationError` (with `QyResolveError`, `QyTypeError`, `QyArityError`, `QyCapabilityError`, `QyEffectError`, `QyRuntimeError`, `QyPythonError`, `QyCancelledError`, `QyTimeoutError`, `QyAggregateError`). `QyEffectSignal` carries effect/continuation for unhandled effects. All errors carry `SourceSpan` and `TraceFrame` for reporting.

- **`values.py`** — Core value types: `QyNil`, `QyT` (boolean), `QyCons`/`QyChain` (cons-based lists), `QyEmptyChain`/`QyEmptyList` sentinels.

- **`analyzer.py`** — Lightweight type checker. Infers types, validates arity, reports `Diagnostic` issues.

- **`formatter.py`** — Canonical pretty-printer. Formats forms with configurable line length and indentation.

- **`runtime.py`** — `Qy` class for Python embedding. Decorator-based operator registration (`@qy.register_pure()`, etc.).

- **`cli.py`** — Typer-based CLI with `run`, `repl`, `fmt`, `ast`, `check`, `lsp`, `operators` commands.

- **`lsp.py`** — pygls-based Language Server (diagnostics, completions, hover, formatting via stdio).

### Standard library (`qy/stdlib/`)

- **`core.py`** — Built-in operators (~1100 lines): arithmetic, list ops, control flow, effect definitions (`defeffect`, `perform`, `handle`, `resume`), predicates, type conversions.
- **`io.py`** — I/O operators (`print`, `echo`).
- **`strings.py`** — String operators (`str-upper`, `str-concat`, `str-split`, `str-join`, etc.).
- **`__init__.py`** — Module loading system. Three prelude modules auto-loaded: `qy.core`, `qy.io`, `qy.str`. Supports file-based modules (`.py` and `.qy`), `register_module()`, and `register_module_loader()`.

### Extension (`extensions/qylang-support-vscode/`)

VSCode extension providing syntax highlighting (TextMate grammar), LSP client integration, formatting, and language configuration. Built with TypeScript, bundled via esbuild.

### Design decisions

- `Symbol()` is a frozen dataclass wrapper with optional source span — prevents Python/Qy value confusion.
- All forms are immutable (frozen dataclasses, tuples).
- Async-first evaluation: all core evaluate functions have async variants; `run_async()` bridges sync callers.
- Effect system uses `QyEffectSignal` for unwinding and `QyContinuation` for resumable effects.
- No relative imports allowed (enforced by ruff TID252).

## Code style

- Ruff with 100-char line length, Google docstring convention
- `isort` with `force-single-line = true`
- Conventional commits (enforced by commitlint + husky)
- Prettier for config files (JSON, TOML, Markdown)
