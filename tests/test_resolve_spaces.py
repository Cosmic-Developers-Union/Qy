# coding: utf-8
"""Tests for the HIR ``resolve.spaces`` pass."""

from __future__ import annotations

from qy.build.artifact import HIR_VALIDATED
from qy.build.pipeline import compile_source_to_kind
from qy.build.pipeline import hir_artifact
from qy.ir.hir import HIRSymbolSpaceLayout
from qy.ir.hir import ProgramIR
from qy.passes.hir.lower import lower_source
from qy.passes.pass_base import PassContext
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
