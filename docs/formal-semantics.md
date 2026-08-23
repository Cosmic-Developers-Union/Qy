# Formal Semantics

This document codifies the formal contract of QyLang's IR layers and compilation
pipeline. It is the canonical human-auditable formalization; the Lean 4
transcription lives under `formal/QyLangFormal.lean`.

**Audience**: a reviewer who wants to know *why* each verifier rule exists,
*which* predicate enforces it, and *which* test exercises it.

## §0 Purpose & Audience

Companion to `hir-spec.md`, `mir-spec.md`, `lir-spec.md`, `ir-design.md`. The
specs define the data shapes; this document defines the **invariants** that the
implementation actually checks and the **theorems** that the pipeline composition
is meant to satisfy.

All formal claims here are tracked against:

- The Python predicate implementations in `qy/ir/<layer>/predicates.py`.
- The Lean 4 skeletons in `formal/QyLangFormal.lean`.

Where the Python and Lean diverge (e.g., the Lean model abstracts over the
concrete `IRExpr` data shapes and tracks only the relevant fragments), this is
explicitly noted in the relevant section.

## §1 Well-formedness predicates

For each IR layer we define one composite predicate that combines the per-rule
checks enumerated in the corresponding spec.

### 1.1 HIR well-formedness

`WF_HIR(P) ≡ ⋀_{i=1..14} H_i(P)`

Each `H_i` is implemented as a pure function `qy.ir.hir.predicates.h<i>_*`
returning `tuple[Diagnostic, ...]`. The top-level `check_program(program)`
walks the program body, recurses through child expressions, and accumulates
diagnostics without mutating the IR.

Cross-references (predicate → spec → test):

- `H1` resolved-symbols → `hir-spec.md §4 H1` → `tests/test_invariants_hir.py::test_h1_*`
- `H2` define-once-in-space → `hir-spec.md §4 H2` → `test_h2_*`
- … (all 14 rules in §7 correspondence table)
- `H14` macro-body-raw-synced → `hir-spec.md §4 H14` → `test_h14_*`

**Implementation notes** (deviations from the strict spec):

- `H3` is relaxed to fire only when `bindings+body` are **both** empty for
  `LetExpr` (zero-arg `let` / `defun` / `lambda` are valid).
- `H4`, `H6`, `H8`, `H9`, and the module-body variant of `H3` are emitted as
  `severity="warning"` because the lowerer intentionally produces patterns
  the strict spec would reject (auto-declared effects, stripped macros, etc.).
- `H11` accepts literal Python atoms (`int`/`str`/`float`/`bool`/`bytes`/`None`)
  and `QyNil` in addition to the spec's `Symbol | Chain` — runtime `evaluate`
  preserves any literal atom inside `(quote ...)`.

### 1.2 MIR well-formedness

`WF_MIR(M) ≡ ⋀_{i=1..12} M_i(M)`

`M1..M8, M11, M12` are pre-existing in `qy.ir.mir.verify_mir`; Phase 1
extracts them into `m1_main_in_range`, etc., and adds `M9`, `M10`.

`M9` (effect-handle pairing): linear scan per function with a stack of
`handle_id`s. `EFFECT_HANDLE_BEGIN(h)` pushes; `EFFECT_HANDLE_END(h)` must
match the stack top. Stack resets at function entry (no cross-function leak).

`M10` (scope nesting): same pattern but for `ENTER_SCOPE` / `EXIT_SCOPE` with
a depth counter. Emitted as `warning` because `lower_let` intentionally
skips `EXIT_SCOPE` after a terminator (the runtime VM drops `frame.env` on
return, so the unbalanced scope never escapes the function boundary).

### 1.3 LIR well-formedness

`WF_LIR(L) ≡ ⋀_{i=1..15} L_i(L)`

`L1`, `L4`, `L13`, `L15` are pre-existing; `L2`, `L5..L12`, `L14` are new in
Phase 1.

`L5..L12` walk the layout fields (`frame_layout`, `continuations`, `handlers`,
`symbol_spaces`). On currently-unpopulated fields they return empty
diagnostics — future-proof: when `symbol_space_layout` / `binding_lowering`
populate them, the verifier turns on automatically.

`L10` mirrors `M10`: `ENTER_SCOPE`/`EXIT_SCOPE` nesting, emitted as
`warning` for the same reason.

## §2 Layer-ownership contract

Restates `ir-design.md §1.1` in predicate form.

For each pass `P_k` in the pipeline, `Layer(P_k) ∈ {hir, mir, lir, bytecode}`.
Passes may only write facts belonging to `Layer(P_k)` — i.e., a pass in layer
`L` may not introduce facts that a consumer at layer `L'` ≠ `L` would rely on.

Concretely:

- `hir.lower` writes only HIR facts.
- `hir.validate` reads HIR facts, emits `Diagnostic`s.
- `mir.lower` reads HIR facts, writes only MIR facts.
- `mir.validate` reads MIR facts, emits `Diagnostic`s.
- `lir.lower` reads MIR facts, writes only LIR facts.
- `lir.verify` reads LIR facts, emits `Diagnostic`s.
- `emit.bytecode` reads LIR facts, writes only bytecode facts.

This is an *audit-level* invariant; the implementation enforces it via
`Pass.input_kind` / `Pass.output_kind` contracts and the pipeline
kind-mismatch check (`Pipeline._PipelineState.kind_mismatch`).

## §3 Small-step operational semantics (informal)

This section sketches a small-step operational semantics for the surface
dialect. It is **informal, not machine-checked**; see `formal/QyLangFormal.lean`
for the Lean 4 transcription of the related well-formedness predicates.

Evaluation contexts `E`:

```
E ::= □
    | (op v_1 ... v_{i-1} E e_{i+1} ... e_n)
    | (if E c a)
    | (let ((x_1 e_1) ... (x_n e_n)) E)
    | (handle E ((eff (params) body)) ...)
    | ...
```

Reductions `e → e'`:

1. **Pure**: `(op v_1 ... v_n) → δ(op, v_1, ..., v_n)` where `δ` is the
   operator's runtime semantics (`qy.core.operator_runtime`).
2. **Control**: `if`, `let`, `lambda`, `cond`, `pipeline` — see
   `language-core-audit.md` §3.
3. **Effect**: `perform`, `handle`, `resume` — see
   `lir-effect-frame-design.md`.
4. **Module**: `from-import`, `module`, `defun` — see `hir-spec.md §5`.

The semantics is intentionally *value-oriented*: chains, tuples, primitive
atoms are all values; only `□`-context redexes step.

## §4 Layer-to-semantics mapping

For each layer we name the subset of the SOS it preserves and the
well-formedness predicate that guards the lowering:

| Layer | Preserves subset of §3 | Guards |
| --- | --- | --- |
| HIR  | Pure + Control + Effect + Module (after surface macro expansion) | `WF_HIR` |
| MIR  | Pure + Control + Effect (no Module — modules are HIR-only) | `WF_MIR` |
| LIR  | Pure + Control + Effect (linearized; effect edges lowered to frame ops) | `WF_LIR` |
| bytecode | Pure + Control + Effect (register-VM instruction encoding) | LIR's `verify_lir` |

The MIR layer no longer carries modules; modules are HIR-only constructs whose
runtime effect is to bind names into a `SymbolSpace`.

## §5 Stated preservation theorems

These theorems are the headline claims of the formalization. They are
**stated** (not proved) in this document; the Lean 4 skeleton in
`formal/QyLangFormal.lean` carries the same statements with `sorry`
placeholders.

**Theorem 1** (HIR lowering preservation).

For all source programs `P`, `lower_hir(P)` produces `H` such that:

1. `WF_HIR(H)` (HIR well-formedness holds after lowering).
2. `⟦H⟧ = ⟦P⟧` (semantic equivalence with the source).

*Proof sketch*: structural induction over the surface grammar. Each surface
form corresponds to exactly one HIR constructor (`hir-spec.md §5`); the
verifier predicates cover the well-formedness side; the lowering is
straight-line code with no semantic side-effects beyond name binding.

**Theorem 2** (HIR → MIR preservation).

For all `H` with `WF_HIR(H)`, `lower_mir(H)` produces `M` such that:

1. `WF_MIR(M)`.
2. `⟦M⟧ = ⟦H⟧`.

*Proof sketch*: HIR → MIR is a control-flow linearization with register
allocation; the MIR predicates (M1-M8) cover the structural well-formedness;
M9/M10 cover effect and scope nesting. Semantic equivalence follows because
MIR is a register-level encoding of the same HIR semantics.

**Theorem 3** (MIR → LIR preservation).

For all `M` with `WF_MIR(M)`, `lower_lir(M)` produces `L` such that:

1. `WF_LIR(L)`.
2. `⟦L⟧ = ⟦M⟧`.

*Proof sketch*: linearization is a no-op; effect edges are lowered to
`EFFECT_*`/`HANDLER_PUSH`/`FRAME_*` ops preserving call/cc-style semantics;
register compaction preserves register equivalence. L1, L3, L4 cover
instruction shape; L2, L5-L12 cover layout; L13/L14 cover dialect purity;
L15 covers continuous-run preservation.

**Theorem 4** (LIR → bytecode preservation).

For all `L` with `WF_LIR(L)`, `compile_lir_bytecode(L)` produces bytecode `B`
such that:

1. `B` is a valid `BytecodeProgram`.
2. `⟦B⟧ = ⟦L⟧`.

*Proof sketch*: encoding is injective on instruction shape (each LIR opcode
maps to exactly one bytecode instruction); the register VM interpreter
implements each opcode's semantics directly (`backend/vm/instance/`).

**Theorem 5** (pipeline composition).

End-to-end `source → bytecode` preserves meaning. By transitivity of
Theorems 1-4:

`⟦compile(source)⟧ = ⟦source⟧`

## §6 Progress & type soundness (informal, conditional)

Restates the 9 core clauses from `language-core-audit.md`. **Future work**:
current `type_name: str` tags are not a type system — they are annotations
that influence lowering but are not checked at runtime. A future refinement
would lift `type_name` to a real type and prove progress + preservation
through the pipeline.

## §7 Verifier ↔ predicate correspondence table

Every H/M/L rule mapped to (a) its predicate function in
`qy/ir/<layer>/predicates.py`, (b) the spec paragraph, (c) the test exercising
it in `tests/test_invariants_<layer>.py`.

| Rule | Predicate function | Spec paragraph | Test |
| --- | --- | --- | --- |
| H1  | `h1_resolved_symbols`           | hir-spec §4 H1  | `test_invariants_hir.py::test_h1_*` |
| H2  | `h2_define_once_in_space`       | hir-spec §4 H2  | `test_invariants_hir.py::test_h2_*` |
| H3  | `h3_node_shape`                 | hir-spec §4 H3  | `test_invariants_hir.py::test_h3_*` |
| H4  | `h4_call_continuous`            | hir-spec §4 H4  | `test_invariants_hir.py::test_h4_*` |
| H5  | `h5_call_tail_position`         | hir-spec §4 H5  | `test_invariants_hir.py::test_h5_*` |
| H6  | `h6_handle_effect_declared`     | hir-spec §4 H6  | `test_invariants_hir.py::test_h6_*` |
| H7  | `h7_resume_in_handler` (via `_h7_in_handler`) | hir-spec §4 H7 | `test_invariants_hir.py::test_h7_*` |
| H8  | `h8_perform_effect_declared`    | hir-spec §4 H8  | `test_invariants_hir.py::test_h8_*` |
| H9  | `h9_module_export_defined`      | hir-spec §4 H9  | `test_invariants_hir.py::test_h9_*` |
| H10 | `h10_from_import_specs_present` | hir-spec §4 H10 | `test_invariants_hir.py::test_h10_*` |
| H11 | `h11_quote_form_is_form`        | hir-spec §4 H11 | `test_invariants_hir.py::test_h11_*` |
| H12 | `h12_define_once_in_space`      | hir-spec §4 H12 | `test_invariants_hir.py::test_h12_*` |
| H13 | `h13_pending_binding_effort`    | hir-spec §4 H13 | `test_invariants_hir.py::test_h13_*` |
| H14 | `h14_macro_body_raw_synced`     | hir-spec §4 H14 | `test_invariants_hir.py::test_h14_*` |
| M1  | `m1_main_in_range`              | mir-spec §4 M1  | `test_invariants_mir.py::test_m1_*` |
| M2  | `m2_unique_block_ids`           | mir-spec §4 M2  | `test_invariants_mir.py::test_m2_*` |
| M3  | `m3_entry_block_exists`         | mir-spec §4 M3  | `test_invariants_mir.py::test_m3_*` |
| M4  | `m4_each_block_has_terminator`  | mir-spec §4 M4  | `test_invariants_mir.py::test_m4_*` |
| M5  | `m5_branch_targets_in_range`    | mir-spec §4 M5  | `test_invariants_mir.py::test_m5_*` |
| M6  | `m6_jump_targets_in_range`      | mir-spec §4 M6  | `test_invariants_mir.py::test_m6_*` |
| M7  | `m7_registers_in_range`         | mir-spec §4 M7  | `test_invariants_mir.py::test_m7_*` |
| M8  | `m8_tail_call_only_terminator`  | mir-spec §4 M8  | `test_invariants_mir.py::test_m8_*` |
| M9  | `m9_effect_handle_pairing`      | mir-spec §4 M9  | `test_invariants_mir.py::test_m9_*` |
| M10 | `m10_scope_nesting`             | mir-spec §4 M10 | `test_invariants_mir.py::test_m10_*` |
| M11 | `m11_unreachable_marked`        | mir-spec §4 M11 | `test_invariants_mir.py::test_m11_*` |
| M12 | `m12_continuous_run`            | mir-spec §4 M12 | `test_invariants_mir.py::test_m12_*` |
| L1  | `l1_register_operands_in_range` | lir-spec §4 L1  | `test_invariants_lir.py::test_l1_*` |
| L2  | `l2_unique_function_ids`        | lir-spec §4 L2  | `test_invariants_lir.py::test_l2_*` |
| L3  | `l3_operand_kind_matches_opcode`| lir-spec §4 L3  | `test_invariants_lir.py::test_l3_*` |
| L4  | `l4_jump_targets_in_range`      | lir-spec §4 L4  | `test_invariants_lir.py::test_l4_*` |
| L5  | `l5_frame_layout_consistent`    | lir-spec §4 L5  | `test_invariants_lir.py::test_l5_*` |
| L6  | `l6_continuation_layout_consistent` | lir-spec §4 L6 | `test_invariants_lir.py::test_l6_*` |
| L7  | `l7_handler_parent_exists`      | lir-spec §4 L7  | `test_invariants_lir.py::test_l7_*` |
| L8  | `l8_slot_address_in_space`      | lir-spec §4 L8  | `test_invariants_lir.py::test_l8_*` |
| L9  | `l9_slot_complete_at_most_once` | lir-spec §4 L9  | `test_invariants_lir.py::test_l9_*` |
| L10 | `l10_scope_nesting`             | lir-spec §4 L10 | `test_invariants_lir.py::test_l10_*` |
| L11 | `l11_handler_push_pop_nesting`  | lir-spec §4 L11 | `test_invariants_lir.py::test_l11_*` |
| L12 | `l12_frame_enter_leave_nesting` | lir-spec §4 L12 | `test_invariants_lir.py::test_l12_*` |
| L13 | `l13_abstract_machine_no_language_opcodes` | lir-spec §4 L13 | `test_invariants_lir.py::test_l13_*` |
| L14 | `l14_compat_no_abstract_machine_opcodes`  | lir-spec §4 L14 | `test_invariants_lir.py::test_l14_*` |
| L15 | `l15_continuous_run`            | lir-spec §4 L15 | `test_invariants_lir.py::test_l15_*` |

## §8 Known gaps

Explicit list of facts the verifier does *not* enforce:

- `continuous` propagation (H4 emitted as `warning`; M12 / L15 are dead until
  `continuous=True` propagates through `lower.py`).
- LIR layout fields unpopulated (L5–L12 currently pass trivially).
- `MIRConstantPool` invariants beyond pool-index range.
- Abstract-machine dialect ops never emitted in production (L14 only checks
  absence; `CONT_INJECT` / `HANDLER_FIND` declared but un-emitted, see
  `lir-spec.md §7.4–7.5`).

## §9 Maintenance protocol

When a new opcode is added or a rule is loosened:

1. The predicate in `qy/ir/<layer>/predicates.py` is updated.
2. The spec paragraph (`hir-spec.md` / `mir-spec.md` / `lir-spec.md`) is
   updated to match.
3. The Lean 4 skeleton in `formal/QyLangFormal.lean` is updated to mirror.
4. The test in `tests/test_invariants_<layer>.py` is added or updated.

This four-step procedure is the *unity* property of the formalization —
keeping the four artifacts synchronized is what makes the verifier trustworthy.
