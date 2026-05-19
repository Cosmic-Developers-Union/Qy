# coding: utf-8
# Tests for HIR node types: DefineExpr, PipelineExpr, ParallelExpr, AllExpr, RaceExpr, ApplyExpr.


from __future__ import annotations

from qy.ir import AllExpr
from qy.ir import ApplyExpr
from qy.ir import DefineExpr
from qy.ir import ParallelExpr
from qy.ir import PipelineExpr
from qy.ir import RaceExpr
from qy.passes.lower_hir import lower_source

# ---------------------------------------------------------------------------
# Lowering tests
# ---------------------------------------------------------------------------


def test_define_lowers_to_define_expr():
    program = lower_source("(define x 42)")
    assert len(program.body) == 1
    node = program.body[0]
    assert isinstance(node, DefineExpr)
    assert node.name.name == "x"


def test_pipeline_lowers_to_pipeline_expr():
    program = lower_source("(pipeline 1 2 3)")
    assert len(program.body) == 1
    node = program.body[0]
    assert isinstance(node, PipelineExpr)
    assert len(node.body) == 3


def test_parallel_lowers_to_parallel_expr():
    program = lower_source("(parallel 1 2)")
    assert len(program.body) == 1
    assert isinstance(program.body[0], ParallelExpr)


def test_all_lowers_to_all_expr():
    program = lower_source("(all 1 2 3)")
    assert len(program.body) == 1
    assert isinstance(program.body[0], AllExpr)


def test_race_lowers_to_race_expr():
    program = lower_source("(race 1 2)")
    assert len(program.body) == 1
    assert isinstance(program.body[0], RaceExpr)


def test_apply_lowers_to_apply_expr():
    program = lower_source("(apply + (quote (1 2)))")
    assert len(program.body) == 1
    assert isinstance(program.body[0], ApplyExpr)


def test_apply_wrong_arity_emits_diagnostic():
    program = lower_source("(apply +)")
    assert not program.ok
    assert any("apply" in d.message for d in program.diagnostics)


def test_pipeline_empty_emits_diagnostic():
    program = lower_source("(pipeline)")
    assert not program.ok
    assert any("pipeline" in d.message for d in program.diagnostics)


def test_define_too_few_args_emits_diagnostic():
    program = lower_source("(define x)")
    assert not program.ok
    assert any("define" in d.message for d in program.diagnostics)


# ---------------------------------------------------------------------------
# Execution tests (IR VM)
# ---------------------------------------------------------------------------


def test_pipeline_executes_sequentially():
    from qy import Qy

    q = Qy()
    result = q.evaluate_source("(pipeline 1 2 3)")
    assert result == 3


def test_pipeline_single_expr():
    from qy import Qy

    q = Qy()
    result = q.evaluate_source("(pipeline 42)")
    assert result == 42


def test_define_binds_value():
    from qy import Qy

    q = Qy()
    result = q.evaluate_source("(define x 99)")
    assert result == 99


def test_parallel_returns_tuple():
    from qy import Qy

    q = Qy()
    result = q.evaluate_source("(parallel 1 2 3)")
    assert result == (1, 2, 3)


def test_all_returns_tuple():
    from qy import Qy

    q = Qy()
    result = q.evaluate_source("(all 10 20)")
    assert result == (10, 20)


def test_race_returns_first():
    from qy import Qy

    q = Qy()
    # With literals all finish instantly; result must be one of the values
    result = q.evaluate_source("(race 1 2 3)")
    assert result in (1, 2, 3)
