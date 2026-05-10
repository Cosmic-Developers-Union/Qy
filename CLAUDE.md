# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Qy is a symbolic Lisp-like language implemented in Python. It provides a minimal core with explicit symbol representation, three-tier operator evaluation, and tooling support (REPL, formatter, type checker, LSP).

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
make lint          # ruff check, ruff format --check, ty check
make lint-fix      # auto-fix lint issues

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

- **`evaluator.py`** — Interpreter with three operator kinds controlling evaluation strategy:
  - `PureOperator` — evaluates all args first, then applies (e.g., `+`, `car`)
  - `EvaluationOperator` — controls evaluation order (e.g., `quote`, `cond`, `let`)
  - `SyntaxOperator` — receives raw unevaluated syntax (e.g., `defun`)
  - `Environment` provides lexical scoping; `UserFunction` implements closures.

- **`analyzer.py`** — Lightweight type checker. Infers types (`number`, `symbol`, `tuple`, `bool`, `function`, etc.), validates arity, and reports `Diagnostic` issues.

- **`formatter.py`** — Canonical pretty-printer. Formats forms with configurable line length and indentation.

- **`runtime.py`** — `Qy` class for Python embedding. Decorator-based operator registration (`@qy.register_pure()`, etc.).

- **`cli.py`** — Typer-based CLI with `run`, `repl`, `fmt`, `ast`, `check`, `lsp` commands.

- **`lsp.py`** — pygls-based Language Server (diagnostics, completions, hover, formatting via stdio).

### Design decisions

- `Symbol()` is a frozen dataclass wrapper, not a bare string — prevents Python/Qy value confusion.
- All forms are immutable (frozen dataclasses, tuples).
- No relative imports allowed (enforced by ruff TID252).

## Code style

- Ruff with 100-char line length, Google docstring convention
- `isort` with `force-single-line = true`
- Conventional commits (enforced by commitlint + husky)
- Prettier for config files (JSON, TOML, Markdown)
