/-
  QyLangFormal.lean — Lean 4 transcription of QyLang's IR well-formedness
  predicates and pipeline preservation theorems.

  This file is the Lean 4 counterpart to `docs/formal-semantics.md`. It
  mirrors the predicate implementations in `qy/ir/<layer>/predicates.py` and
  the prose preservation theorems in §5 of the formal-semantics doc.

  ## Verification status

  This file builds with `lake build` (Lean 4.33.1). The well-formedness
  predicates (§1) are defined as `Prop`-valued functions over inductive types
  that abstract the relevant fragments of the Python IR. The preservation
  theorems (§5) are stated with `sorry` placeholders — replacing them with
  real proofs is a substantial effort and depends on a Mathlib upgrade.

  ## Build

      cd formal
      lake build

  Or equivalently, with elan installed:

      PATH=$HOME/.elan/bin:$PATH lake build
-/

namespace QyLangFormal

/-! ## §1.1 HIR well-formedness predicates

Mirror of `qy/ir/hir/predicates.py`. We model the relevant HIR fragment as
an inductive type and define each `H_i` as a predicate over it.
-/

namespace HIR

/-- A symbol name. The Python code uses `Symbol` (a dataclass with a `name`
    field); we abstract the name as `String`. -/
abbrev SymbolName := String

/-- A symbol space: a name plus a list of bound symbol names. The Python
    implementation uses `dict[Symbol, Binding]`; we model only the names
    because well-formedness predicates only need to know *which* symbols
    are bound, not what they're bound to. -/
structure SymbolSpace where
  name : SymbolName
  bindings : List SymbolName
  deriving Repr

/-- A literal atom accepted inside `(quote ...)`. The Python verifier
    accepts Python's `int`/`str`/`float`/`bool`/`bytes`/`None` plus
    `QyNil`; we abstract these. -/
inductive LiteralAtom : Type where
  | intLit (n : Int)
  | strLit (s : String)
  | boolLit (b : Bool)
  | nilLit
  deriving Repr

/-- Quote form fragment. Mirrors `Form` from `qy/frontend/form.py`. -/
inductive IRForm : Type where
  | symbol (name : SymbolName)
  | chain (head : SymbolName) (tail : IRForm)
  | tuple (items : List IRForm)
  | literal (atom : LiteralAtom)
  deriving Repr

/-- HIR expression fragment. We model only the constructors the verifier
    rules reason about. No-op constructors (those that don't affect any
    predicate) are abstracted away. -/
inductive IRExpr : Type where
  | symbolRef (name : SymbolName)
  | call (op : SymbolName) (args : List IRExpr)
      (tail_position : Bool) (continuous : Bool)
  | define (name : SymbolName) (value : IRExpr)
  | lambda_ (params : List SymbolName) (body : List IRExpr)
  | let_ (bindings : List (SymbolName × IRExpr)) (body : List IRExpr)
  | cond (clauses : List (IRExpr × IRExpr))
  | handle (expr : Option IRExpr) (handlers : List IRExpr)
  | perform (effect : SymbolName)
  | resume (effect : SymbolName) (k : IRExpr)
  | quote (form : IRForm)
  | module (name : SymbolName) (body : List IRExpr) (export_names : List SymbolName)
  | fromImport (module_name : SymbolName) (specs : List SymbolName)
  deriving Repr

/-- H1: every `symbolRef.name` is non-empty (`binding is not None` in the
    Python verifier). -/
def H1_resolved_symbols (e : IRExpr) : Prop :=
  match e with
  | .symbolRef name => name ≠ ""
  | _ => True

/-- H2: a SymbolSpace has at most one binding per symbol. -/
def H2_define_once_in_space (space : SymbolSpace) : Prop :=
  ∀ s : SymbolName, (space.bindings.filter (· = s)).length ≤ 1

/-- H3 (relaxed): an expression with both empty bindings AND empty body is
    invalid. The strict spec also requires `bindings ≥ 1` and `body ≥ 1`
    individually; the Python implementation relaxes this so zero-arg
    `let`/`defun`/`lambda` are accepted. -/
def H3_let_shape (b : List (SymbolName × IRExpr)) (body : List IRExpr) : Prop :=
  ¬ (b.isEmpty ∧ body.isEmpty)

def H3_handle_shape (e : Option IRExpr) (hs : List IRExpr) : Prop :=
  ¬ (e.isNone ∧ hs.isEmpty)

def H3_module_shape (body : List IRExpr) : Prop :=
  ¬ body.isEmpty

/-- H4: `continuous=True` only valid when the operator is known-pure.
    We abstract "known-pure" as `op ∈ known_pure_ops`. -/
def H4_call_continuous (known_pure : List SymbolName) (e : IRExpr) : Prop :=
  match e with
  | .call op _ _ true => op ∈ known_pure
  | _ => True

/-- H5: tail-position only set in valid positions. We model the abstract
    property: `tail_position = true` only when the call is the last in its
    container. Conservatively, we say no call is tail-position in this
    fragment — the Python verifier's full walk tracks parent context. -/
def H5_call_tail_position (e : IRExpr) : Prop :=
  match e with
  | .call _ _ true _ => False
  | _ => True

/-- H6: `HandleExpr` references only declared effects. -/
def H6_handle_effect_declared (declared : List SymbolName) (e : IRExpr) : Prop :=
  match e with
  | .handle _ handlers =>
      ∀ h, h ∈ handlers →
        match h with
        | .symbolRef name => name ∈ declared
        | _ => True
  | _ => True

/-- H7: `ResumeExpr` only inside a handler body. We model this as: `resume`
    not at the top level. The Python verifier threads a `current_effect`
    field on `Scope`; full recursive walk omitted for brevity. -/
def H7_resume_in_handler (e : IRExpr) : Prop :=
  match e with
  | .resume _ _ => False
  | _ => True

/-- H8: `PerformExpr.effect` must be declared. -/
def H8_perform_effect_declared (declared : List SymbolName) (e : IRExpr) : Prop :=
  match e with
  | .perform effect => effect ∈ declared
  | _ => True

/-- Helper: collect names defined by top-level define/lambda forms. -/
def collectDefinedNames : List IRExpr → List SymbolName
  | [] => []
  | .define n _ :: rest => n :: collectDefinedNames rest
  | _ :: rest => collectDefinedNames rest

/-- H9: every export name is defined in the module body. -/
def H9_module_export_defined (e : IRExpr) : Prop :=
  match e with
  | .module _ body exports =>
      ∀ n, n ∈ exports → n ∈ collectDefinedNames body
  | _ => True

/-- H10: every `from-import` spec must be in the target's export view.
    The export view is supplied as a function `module → exports`. -/
def H10_from_import_specs_present
    (target_exports : SymbolName → List SymbolName) (e : IRExpr) : Prop :=
  match e with
  | .fromImport target specs =>
      ∀ s, s ∈ specs → s ∈ target_exports target
  | _ => True

/-- H11: `QuoteExpr.form` is a legal `IRForm`. The type system enforces
    this statically (the field has type `IRForm`); the predicate is
    trivially true here. -/
def H11_quote_form_is_form (e : IRExpr) : Prop :=
  match e with
  | .quote _ => True
  | _ => True

/-- H12: a `define` name must not already be bound in the current space. -/
def H12_define_once_in_space (space : SymbolSpace) (e : IRExpr) : Prop :=
  match e with
  | .define name _ => name ∉ space.bindings
  | _ => True

/-- H13: pending-binding effort (placeholder; the Python implementation
    tracks which bindings have been computed). -/
def H13_pending_binding_effort (_ : IRExpr) : Prop := True

/-- H14: macro body / raw body synced (placeholder; macros are stripped
    in `macro.expand` before HIR). -/
def H14_macro_body_raw_synced (_ : IRExpr) : Prop := True

/-- `WF_HIR(P)`: the conjunction of all H1-H14 predicates applied to a
    whole program. -/
def WF_HIR
    (declared : List SymbolName)
    (target_exports : SymbolName → List SymbolName)
    (space : SymbolSpace)
    (program : IRExpr) : Prop :=
  H1_resolved_symbols program ∧
  H2_define_once_in_space space ∧
  (∀ b body, program = .let_ b body → H3_let_shape b body) ∧
  (∀ e hs, program = .handle e hs → H3_handle_shape e hs) ∧
  H4_call_continuous declared program ∧
  H5_call_tail_position program ∧
  H6_handle_effect_declared declared program ∧
  H7_resume_in_handler program ∧
  H8_perform_effect_declared declared program ∧
  H9_module_export_defined program ∧
  H10_from_import_specs_present target_exports program ∧
  H11_quote_form_is_form program ∧
  H12_define_once_in_space space program ∧
  H13_pending_binding_effort program ∧
  H14_macro_body_raw_synced program

end HIR

/-! ## §1.2 MIR well-formedness predicates

Mirror of `qy/ir/mir/predicates.py` — we focus on M9 (effect handle pairing)
and M10 (scope nesting), which are new in Phase 1. -/

namespace MIR

/-- A MIR instruction fragment. We model only the opcodes that the M-rules
    reason about. -/
inductive MIRInstr : Type where
  | enterScope
  | exitScope
  | effectHandleBegin (handleId : Nat)
  | effectHandleEnd (handleId : Nat)
  | other (label : String)
  deriving Repr

/-- A MIR block is a list of instructions. -/
abbrev MIRBlock := List MIRInstr

/-- M9: `EFFECT_HANDLE_BEGIN(h)` and `EFFECT_HANDLE_END(h)` are paired within
    the same function, and stack-disciplined. We model this with a
    tail-recursive walker maintaining a stack of active handle IDs. -/
def M9_effect_handle_pairing_aux : MIRBlock → List Nat → Prop
  | [], _ => True
  | .effectHandleBegin h :: rest, stack =>
      M9_effect_handle_pairing_aux rest (h :: stack)
  | .effectHandleEnd h :: rest, h' :: stack =>
      h = h' ∧ M9_effect_handle_pairing_aux rest stack
  | .effectHandleEnd _ :: [], [] => False
  | .effectHandleEnd _ :: (_ :: _), [] => False
  | _ :: rest, stack => M9_effect_handle_pairing_aux rest stack

def M9_effect_handle_pairing (block : MIRBlock) : Prop :=
  M9_effect_handle_pairing_aux block []

/-- M10: ENTER_SCOPE / EXIT_SCOPE are balanced. -/
def M10_scope_nesting_aux : MIRBlock → Nat → Prop
  | [], depth => depth = 0
  | .enterScope :: rest, depth => M10_scope_nesting_aux rest (depth + 1)
  | .exitScope :: rest, depth =>
      depth > 0 ∧ M10_scope_nesting_aux rest (depth - 1)
  | _ :: rest, depth => M10_scope_nesting_aux rest depth

def M10_scope_nesting (block : MIRBlock) : Prop :=
  M10_scope_nesting_aux block 0

end MIR

/-! ## §1.3 LIR well-formedness predicates

Mirror of `qy/ir/lir/predicates.py`. We focus on L2 (unique function IDs / main
in range) and L10 (scope nesting) — both new in Phase 1. -/

namespace LIR

/-- A LIR function fragment: just a name and an instruction stream. -/
structure LIRFunction where
  name : String
  instructions : List String
  deriving Repr

/-- A LIR program. -/
structure LIRProgram where
  functions : List LIRFunction
  main : Nat
  deriving Repr

/-- L2: main is a valid index into `functions`. (Tuple index uniqueness is
    built into `List`.) -/
def L2_unique_function_ids (p : LIRProgram) : Prop :=
  p.main < p.functions.length

/-- L10: a single function's ENTER_SCOPE / EXIT_SCOPE are balanced. -/
def L10_scope_nesting_aux : List String → Nat → Prop
  | [], depth => depth = 0
  | "ENTER_SCOPE" :: rest, depth => L10_scope_nesting_aux rest (depth + 1)
  | "EXIT_SCOPE" :: rest, depth =>
      depth > 0 ∧ L10_scope_nesting_aux rest (depth - 1)
  | _ :: rest, depth => L10_scope_nesting_aux rest depth

def L10_scope_nesting (f : LIRFunction) : Prop :=
  L10_scope_nesting_aux f.instructions 0

end LIR

/-! ## §5 Preservation theorems (statements only)

These mirror §5 of `docs/formal-semantics.md`. The theorem statements are
intentionally abstract — we don't model the surface syntax or the lowering
functions concretely, but we set up the framework so future work can fill in
the proofs.

The `lower_*` functions are abstract placeholders; concrete implementations
in Python live in `qy/passes/<src>/lower.py`. -/

/-- A surface program: just a string of source text. -/
structure SourceProgram where
  text : String
  deriving Repr

/-- MIR program: a list of MIR blocks. -/
structure MIRProgram' where
  functions : List MIR.MIRBlock
  deriving Repr

/-- Abstract lowering functions. -/
axiom lower_hir : SourceProgram → HIR.IRExpr
axiom lower_mir : HIR.IRExpr → MIRProgram'
axiom lower_lir : MIRProgram' → LIR.LIRProgram
axiom compile_lir_bytecode : LIR.LIRProgram → String  -- bytecode is a string blob

/-- Semantic denotation (intended meaning). Abstract; we don't model values
    concretely. `Sum` from `Init.Prelude` distinguishes the four layers. -/
inductive Layer : Type where
  | source
  | hir
  | mir
  | lir
  | bytecode
  deriving DecidableEq, Repr

axiom denot : SourceProgram → HIR.IRExpr → MIRProgram' → LIR.LIRProgram →
              String → Layer → String

/-- **Theorem 1** (HIR lowering preservation).

    For all source programs `P`, lowering to HIR yields a well-formed HIR
    whose meaning equals the source's meaning. -/
theorem hir_lowering_preserves_meaning
    (declared : List HIR.SymbolName)
    (target_exports : HIR.SymbolName → List HIR.SymbolName)
    (space : HIR.SymbolSpace)
    (p : SourceProgram) :
    HIR.WF_HIR declared target_exports space (lower_hir p) ∧
    denot p (lower_hir p) (lower_mir (lower_hir p))
           (lower_lir (lower_mir (lower_hir p)))
           (compile_lir_bytecode (lower_lir (lower_mir (lower_hir p))))
           Layer.source =
    denot p (lower_hir p) (lower_mir (lower_hir p))
           (lower_lir (lower_mir (lower_hir p)))
           (compile_lir_bytecode (lower_lir (lower_mir (lower_hir p))))
           Layer.hir := by
  sorry

/-- **Theorem 2** (HIR → MIR preservation). -/
theorem hir_to_mir_preserves_meaning
    (declared : List HIR.SymbolName)
    (target_exports : HIR.SymbolName → List HIR.SymbolName)
    (space : HIR.SymbolSpace)
    (h : HIR.IRExpr)
    (hWF : HIR.WF_HIR declared target_exports space h) :
    (∀ blk, blk ∈ (lower_mir h).functions →
            MIR.M9_effect_handle_pairing blk ∧ MIR.M10_scope_nesting blk) ∧
    denot { text := "" } h (lower_mir h)
           (lower_lir (lower_mir h))
           (compile_lir_bytecode (lower_lir (lower_mir h)))
           Layer.hir =
    denot { text := "" } h (lower_mir h)
           (lower_lir (lower_mir h))
           (compile_lir_bytecode (lower_lir (lower_mir h)))
           Layer.mir := by
  sorry

/-- **Theorem 3** (MIR → LIR preservation). -/
theorem mir_to_lir_preserves_meaning
    (m : MIRProgram')
    (mWF : ∀ blk, blk ∈ m.functions →
            MIR.M9_effect_handle_pairing blk ∧ MIR.M10_scope_nesting blk) :
    LIR.L2_unique_function_ids (lower_lir m) ∧
    (∀ f, f ∈ (lower_lir m).functions → LIR.L10_scope_nesting f) ∧
    denot { text := "" } (HIR.IRExpr.symbolRef "") m (lower_lir m)
           (compile_lir_bytecode (lower_lir m))
           Layer.mir =
    denot { text := "" } (HIR.IRExpr.symbolRef "") m (lower_lir m)
           (compile_lir_bytecode (lower_lir m))
           Layer.lir := by
  sorry

/-- **Theorem 4** (LIR → bytecode preservation).

    Stated abstractly; the concrete proof would argue by injectivity of the
    instruction encoding (each LIR opcode → exactly one bytecode
    instruction) plus correctness of the register VM's per-opcode
    semantics. -/
theorem lir_to_bytecode_preserves_meaning
    (l : LIR.LIRProgram)
    (lWF : LIR.L2_unique_function_ids l ∧
           (∀ f, f ∈ l.functions → LIR.L10_scope_nesting f)) :
    denot { text := "" } (HIR.IRExpr.symbolRef "") { functions := [] } l
           (compile_lir_bytecode l)
           Layer.lir =
    denot { text := "" } (HIR.IRExpr.symbolRef "") { functions := [] } l
           (compile_lir_bytecode l)
           Layer.bytecode := by
  sorry

/-- **Theorem 5** (pipeline composition). End-to-end preservation. -/
theorem pipeline_composition
    (declared : List HIR.SymbolName)
    (target_exports : HIR.SymbolName → List HIR.SymbolName)
    (space : HIR.SymbolSpace)
    (p : SourceProgram) :
    denot p (lower_hir p) (lower_mir (lower_hir p))
           (lower_lir (lower_mir (lower_hir p)))
           (compile_lir_bytecode (lower_lir (lower_mir (lower_hir p))))
           Layer.source =
    denot p (lower_hir p) (lower_mir (lower_hir p))
           (lower_lir (lower_mir (lower_hir p)))
           (compile_lir_bytecode (lower_lir (lower_mir (lower_hir p))))
           Layer.bytecode := by
  sorry

end QyLangFormal
