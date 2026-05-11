# Qy Language Draft

Qy is a small symbolic language hosted by Python.

The core language is considered closed after the current set of forms and data types. Future growth should happen in libraries, host operators, analyzers, or runtime policy, not by adding new core semantics.

## Source

Qy source is a stream of forms.

- `abc` is a symbol.
- `"abc"` is also a symbol with text content `abc`.
- `(f a b)` is a tuple form and evaluates as a call.
- `'x` is syntax sugar for `(quote x)`.
- `;` starts a line comment.

Qy currently has no separate string value. Text is represented as `Symbol`.

## Values

Core values:

- `nil`
- `true`, `false`
- integers and floats
- symbols
- tuples
- lists
- dicts
- sets
- operators
- continuations
- effect definitions
- host object references

Tuples are immutable symbolic sequences and are also the source-level call form. Lists, dicts, and sets are runtime data values used for host interop and normal data processing.

## Evaluation

Evaluation rules:

- A symbol resolves in the current lexical environment.
- Built-in literals resolve as `nil`, booleans, integers, or floats.
- A non-empty tuple evaluates its first item as operator and applies it.
- `quote` returns its argument without evaluation.
- A body evaluates forms in order and returns the last value.

Unresolved symbols are errors in normal evaluation. Some text/data boundary operators, such as `print`, `str-*`, `py`, `tuple`, `list`, `dict`, and `set`, preserve unresolved symbol arguments as symbol values.

If a symbol name is already bound, it resolves to that binding. Use `quote` to force a symbol value, for example `'py`.

## Scope

Core scope forms:

- `(let ((name expr) ...) body...)`
- `(lambda (arg ...) body...)`
- `(defun name (arg ...) body...)`
- `(component name (arg ...) body...)`
- `(module name body...)`
- `(from module import name as alias ...)`

Qy uses lexical scope. Functions, components, and macros close over their definition environment.

## Data Operators

Constructors:

- `(tuple value...)`
- `(list value...)`
- `(dict key value...)`
- `(set value...)`

Predicates:

- `(tuple? value)`
- `(list? value)`
- `(dict? value)`
- `(set? value)`

Access:

- `(len value)`
- `(get collection key [default])`
- `(has? collection key)`

`car`, `cdr`, and `cons` work on tuples and lists.

## Effects

Core effect forms:

- `(defeffect name)`
- `(defeffect name :resumable false)`
- `(perform effect arg)`
- `(handle expr ((effect (arg k) body...) ...))`
- `(resume k value)`

`perform` raises an effect. `handle` catches matching effects. `resume` continues a resumable effect continuation.

Non-resumable effects may be handled like catch, but attempting to resume them raises `QY_EFFECT_ERROR`.

Built-in non-resumable effects:

- `python-error`
- `assert-failed`

## Assert

`(assert condition [message])` is a debug operator.

If `condition` is truthy, it returns the condition value. If it is falsey, it performs `assert-failed` with `message` or `assertion failed`.

`assert-failed` is not resumable.

## Async

Qy runs on Python async runtime.

Async operators:

- `(spawn expr)`
- `(await expr...)`
- `(parallel expr...)`
- `(cache expr)`
- `(py source :name value ...)`

`parallel` preserves multiple failures as `QY_AGGREGATE_ERROR`.

## Python Interop

`py` embeds Python code and compiles it as an async function.

Qy to Python:

- `nil` -> `None`
- bool/int/float -> same Python value
- `Symbol` -> `str`
- tuple -> `tuple`
- list -> `list`
- dict -> `dict`
- set -> `set`
- Qy callable -> async Python callable
- host object reference -> wrapped Python object

Python to Qy:

- `None` -> `nil`
- bool/int/float -> same Qy value
- `str` -> `Symbol`
- `tuple` -> tuple
- `list` -> list
- `dict` -> dict
- `set` -> set
- other Python object -> `HostObjectRef`

Python exceptions inside `py` become the non-resumable `python-error` effect.

## Errors

All Qy errors derive from `QyError`.

Errors carry:

- stable code
- message
- source span
- Qy trace frames
- cause
- metadata

Native Python exceptions are wrapped at host boundaries. User-facing output is short by default; debug output may include the Python traceback.

## Static Analysis

The analyzer is intentionally lightweight.

It checks syntax, unresolved symbols, basic arity, basic type expectations, and declared effects. It does not yet provide a complete effect type system or prove that every effect is handled.
