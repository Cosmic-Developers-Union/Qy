# coding: utf-8
"""Tests for the HIR ``resolve.spaces`` pass."""

from __future__ import annotations

from qy.build.artifact import HIR_VALIDATED
from qy.build.pipeline import bytecode_artifact
from qy.build.pipeline import compile_source_to_bytecode
from qy.build.pipeline import compile_source_to_kind
from qy.build.pipeline import hir_artifact
from qy.build.pipeline import lir_artifact
from qy.build.pipeline import mir_artifact
from qy.ir.hir import HIRSymbolSpaceLayout
from qy.ir.hir import ProgramIR
from qy.passes.hir.lower import lower_source
from qy.passes.pass_base import PassContext
from qy.passes.pass_base import PipelineOptions
from qy.passes.pass_base import PipelineSession
from qy.passes.resolve.spaces import ResolveSpacesPass
from qy.passes.resolve.spaces import collect_symbol_spaces
from qy.session.runtime_space import create_standard_runtime_space


def _layout(source: str) -> tuple[HIRSymbolSpaceLayout, ...]:
    return collect_symbol_spaces(lower_source(source))


def test_let_binding_gets_a_slot():
    layouts = _layout("(let ((x 1)) x)")

    slots = {slot.symbol.name: slot for layout in layouts for slot in layout.slots}
    assert slots["x"].index == 0
    assert slots["x"].source == "let-binding"


def test_lambda_params_get_slots_and_parent():
    layouts = _layout("(let ((f (lambda (a b) a))) (f 1 2))")

    by_name = {layout.name: layout for layout in layouts}
    assert "lambda" in by_name
    lambda_layout = by_name["lambda"]
    assert {slot.symbol.name for slot in lambda_layout.slots} == {"a", "b"}
    assert all(slot.source == "lambda-param" for slot in lambda_layout.slots)
    # parent link points at the enclosing let space
    assert lambda_layout.parent is not None
    assert by_name["let"].id == lambda_layout.parent


def test_defun_body_space_parents_top_level():
    layouts = _layout(
        """
        (let ()
          (defun sum-to (n acc)
            (cond ((= n 0) acc) (true acc)))
          (sum-to 1 2))
        """
    )

    by_name = {layout.name: layout for layout in layouts}
    assert "defun:sum-to" in by_name
    defun_layout = by_name["defun:sum-to"]
    assert {slot.symbol.name for slot in defun_layout.slots} == {"n", "acc"}
    assert defun_layout.parent == by_name["let"].id


def test_profile_spaces_are_filtered_out():
    layouts = _layout("(let ((x 1)) x)")

    # Only lexical spaces created by lowering; the pre-symbol-space-chain
    # profile spaces (lisp-ss / number-ss / stdlib, all builtin bindings) are
    # not part of the program layout.
    assert all(layout.name in {"let", "lambda", "Main", "defun:sum-to"} for layout in layouts)


def test_layout_sinks_from_hir_to_mir_and_lir():
    from qy.build.artifact import HIR
    from qy.build.artifact import LIR
    from qy.build.artifact import MIR
    from qy.build.pipeline import lir_artifact
    from qy.build.pipeline import mir_artifact

    source = "(let ((f (lambda (a b) a))) (f 1 2))"
    env = create_standard_runtime_space()
    hir = hir_artifact(compile_source_to_kind(source, PipelineSession(env=env), kind=HIR))
    mir = mir_artifact(compile_source_to_kind(source, PipelineSession(env=env), kind=MIR))
    lir = lir_artifact(compile_source_to_kind(source, PipelineSession(env=env), kind=LIR))

    assert hir.symbol_spaces
    assert hir.symbol_spaces == mir.symbol_spaces
    assert mir.symbol_spaces == lir.symbol_spaces


def test_resolve_spaces_pass_is_in_default_pipeline_and_survives_validation():
    result = compile_source_to_kind(
        "(let ((x 1)) x)",
        PipelineSession(env=create_standard_runtime_space()),
        kind=HIR_VALIDATED,
    )
    program = hir_artifact(result)

    assert program.symbol_spaces, "resolve.spaces output should survive hir.validate"
    assert any(slot.symbol.name == "x" for layout in program.symbol_spaces for slot in layout.slots)


def test_resolve_spaces_pass_is_idempotent():
    program = lower_source("(let ((x 1)) x)")
    first = ResolveSpacesPass().run(PassContext(input_artifact=program, artifact_kind="hir"))
    second = ResolveSpacesPass().run(
        PassContext(input_artifact=first.artifact, artifact_kind="hir")
    )

    assert isinstance(first.artifact, ProgramIR)
    assert isinstance(second.artifact, ProgramIR)
    assert first.artifact.symbol_spaces == second.artifact.symbol_spaces


def test_layout_survives_into_bytecode_program():
    """HIR 下沉的 layout 必须一路到达 bytecode，不得在 backend 边界丢失。."""
    result = compile_source_to_bytecode(
        "(define x 1) (+ x 1)",
        PipelineSession(env=create_standard_runtime_space()),
        options=PipelineOptions(error_threshold=10**6),
    )
    program = bytecode_artifact(result)

    assert program.symbol_spaces
    assert any(slot.symbol.name == "x" for layout in program.symbol_spaces for slot in layout.slots)


def _am_program(source: str):
    result = compile_source_to_kind(
        source,
        PipelineSession(env=create_standard_runtime_space()),
        kind="lir",
        options=PipelineOptions(error_threshold=10**6, lir_dialect="abstract-machine"),
    )
    return lir_artifact(result)


def test_mir_scope_ops_carry_program_layout_space_id():
    """MIR 的 ENTER_SCOPE/EXIT_SCOPE 携带 program-level layout 的 space id。."""
    result = compile_source_to_kind(
        "(let ((x 1)) x)",
        PipelineSession(env=create_standard_runtime_space()),
        kind="mir",
        options=PipelineOptions(error_threshold=10**6),
    )
    program = mir_artifact(result)
    space_ids = {space.id for space in program.symbol_spaces}
    scope_ops = [
        inst
        for function in program.functions
        for block in function.blocks
        for inst in block.instructions
        if inst.opcode in ("ENTER_SCOPE", "EXIT_SCOPE")
    ]

    assert scope_ops, "expected the let to open a scope"
    assert all(len(inst.operands) == 1 for inst in scope_ops)
    assert all(inst.operands[0] in space_ids for inst in scope_ops)


def test_define_slots_resolve_for_main_let_and_function_bodies():
    """顶层 / let / 函数体内的 define 都解析到同一份 program-level layout 的 slot。."""
    program = _am_program(
        """
        (define top 1)
        (defun f (a)
          (define inner 2)
          (let ((z 3)) (define nested 4))
          (+ a inner))
        (f 5)
        """
    )

    layout = {space.name: space for space in program.symbol_spaces}
    assert "Main" in layout
    assert "defun:f" in layout

    addresses = [
        inst.operands[0]
        for function in program.functions
        for inst in function.instructions
        if inst.opcode == "SLOT_COMPLETE"
    ]
    assert addresses, "expected SLOT_COMPLETE for defines"

    # 顶层 define 落在 Main space
    main_ids = {slot.index for slot in layout["Main"].slots}
    assert any(
        address.space == layout["Main"].id and address.slot in main_ids for address in addresses
    )

    # 函数体 define 落在该函数的 space
    defun_ids = {slot.index for slot in layout["defun:f"].slots}
    assert any(
        address.space == layout["defun:f"].id and address.slot in defun_ids for address in addresses
    )

    # 所有地址都必须指向 program-level layout 中存在的 space/slot
    for address in addresses:
        assert address.space in {space.id for space in program.symbol_spaces}


def test_assign_symbol_spaces_keeps_define_once_without_layout_slot():
    """没有 program-level slot 时不得臆造地址：DEFINE_ONCE 原样保留。."""
    from qy.core.syntax import Symbol
    from qy.ir.lir import LIRInstruction
    from qy.passes.lir.spaces import assign_symbol_spaces

    instructions = [LIRInstruction("DEFINE_ONCE", (Symbol("ghost"), 0))]
    rewritten = assign_symbol_spaces(instructions, program_layout=())

    assert [inst.opcode for inst in rewritten] == ["DEFINE_ONCE"]
