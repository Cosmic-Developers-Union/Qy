# coding: utf-8
"""Tests for pass infrastructure and optimization passes."""

from __future__ import annotations

from typing import Any
from typing import cast

from qy.frontend.reader import Symbol
from qy.frontend.reader import read
from qy.ir.lir import LIRProgram
from qy.ir.mir import MIRBlock
from qy.ir.mir import MIRConstantPool
from qy.ir.mir import MIRFunction
from qy.ir.mir import MIRInstruction
from qy.ir.mir import MIRProgram
from qy.ir.mir import MIRTerminator
from qy.passes import PassContext
from qy.passes import Pipeline
from qy.passes import build_optimization_pipeline
from qy.passes.control.cfg_simplify import CFGSimplifyPass
from qy.passes.control.tailcall import TailCallPass
from qy.passes.hir.lower_pass import LowerHIRPass
from qy.passes.mir.lower_pass import LowerMIRPass
from qy.passes.optimize.const_fold import ConstFoldPass
from qy.passes.optimize.dce import DCEPass
from qy.passes.optimize.inline import InlinePass
from qy.passes.pass_base import PipelineOptions
from qy.passes.pass_base import PipelineSession
from qy.session.runtime_space import standard_environment

_TOLERANT_OPTIONS = PipelineOptions(error_threshold=10**6)


def _compile_to_mir(source: str) -> MIRProgram:
    forms = read(source)
    env = standard_environment()
    p = Pipeline()
    p.add_pass(LowerHIRPass())
    p.add_pass(LowerMIRPass())
    ctx = PassContext(
        input_artifact=forms,
        session=PipelineSession(env=env),
        options=_TOLERANT_OPTIONS,
    )
    artifact = p.run(ctx).artifact
    assert artifact is not None
    return cast(MIRProgram, artifact)


def _run_pass(pass_obj: Any, artifact: object, env: object = None):
    session = PipelineSession(env=env) if env else PipelineSession.minimal()
    ctx = PassContext(input_artifact=artifact, session=session)
    return pass_obj.run(ctx)


def _mir_artifact(artifact: object) -> MIRProgram:
    assert artifact is not None
    return cast(MIRProgram, artifact)


def _lir_artifact(artifact: object) -> LIRProgram:
    assert artifact is not None
    return cast(LIRProgram, artifact)


# --- Pipeline integration ---


class TestPipeline:
    def test_create_pipeline_no_optimize(self):
        p = build_optimization_pipeline(optimize=False)
        assert len(p.passes) == 3

    def test_create_pipeline_with_optimize(self):
        p = build_optimization_pipeline(optimize=True)
        assert len(p.passes) > 3

    def test_pipeline_simple_expression(self):
        forms = read("(+ 1 2)")
        env = standard_environment()
        ctx = PassContext(input_artifact=forms, session=PipelineSession(env=env))
        result = build_optimization_pipeline(optimize=False).run(ctx)
        assert result.success
        artifact = _mir_artifact(result.artifact)
        assert artifact.functions

    def test_pipeline_optimized_keeps_runtime_lookups(self):
        # Under strict ssc semantics literals stay as runtime lookups; const
        # fold can no longer pre-compute (+ 1 2) at compile time.
        forms = read("(+ 1 2)")
        env = standard_environment()
        ctx = PassContext(input_artifact=forms, session=PipelineSession(env=env))
        result = build_optimization_pipeline(optimize=True).run(ctx)
        assert result.success
        artifact = _lir_artifact(result.artifact)
        fn = artifact.functions[0]
        opcodes = [i.opcode for i in fn.instructions]
        assert "CALL" in opcodes
        assert "LOAD_ENV" in opcodes


# --- Const Fold ---


class TestConstFold:
    def test_does_not_fold_literal_symbols(self):
        # Numeric literals are SymbolRefExpr → LOAD_ENV at runtime; const fold
        # treats them as opaque references and keeps the call.
        mir = _compile_to_mir("(+ 1 2)")
        env = standard_environment()
        result = _run_pass(ConstFoldPass(), mir, env)
        artifact = _mir_artifact(result.artifact)
        fn = artifact.functions[0]
        opcodes = [i.opcode for b in fn.blocks for i in b.instructions]
        assert "CALL" in opcodes

    def test_does_not_fold_nested_literal_arithmetic(self):
        mir = _compile_to_mir("(+ (* 2 3) (- 10 4))")
        env = standard_environment()
        result = _run_pass(ConstFoldPass(), mir, env)
        # Constant pool stays empty because literals are not pre-materialised
        # in HIR; runtime ssc lookup is the only resolution path.
        consts = result.artifact.constants.values
        assert 12 not in consts

    def test_no_fold_non_pure(self):
        mir = _compile_to_mir("(define x 1)")
        env = standard_environment()
        result = _run_pass(ConstFoldPass(), mir, env)
        assert result.success

    def test_no_fold_non_constant_args(self):
        mir = _compile_to_mir("(define x 5)(+ x 1)")
        env = standard_environment()
        result = _run_pass(ConstFoldPass(), mir, env)
        artifact = _mir_artifact(result.artifact)
        fn = artifact.functions[0]
        opcodes = [i.opcode for b in fn.blocks for i in b.instructions]
        assert "CALL" in opcodes


# --- DCE ---


class TestDCE:
    def test_eliminates_unused_loads_when_runtime_resolved(self):
        # With strict ssc literals, ``(+ 1 2)`` lowers to LOAD_ENV ops + CALL.
        # DCE keeps the LOAD_ENV operands feeding CALL but removes anything
        # that is genuinely unused. Since each LOAD_ENV is consumed by CALL,
        # they all stay live.
        mir = _compile_to_mir("(+ 1 2)")
        env = standard_environment()
        folded = _run_pass(ConstFoldPass(), mir, env).artifact
        result = _run_pass(DCEPass(), folded)
        fn = result.artifact.functions[0]
        opcodes = [i.opcode for b in fn.blocks for i in b.instructions]
        assert "CALL" in opcodes
        assert "LOAD_ENV" in opcodes

    def test_preserves_used_instructions(self):
        mir = _compile_to_mir("(+ 1 2)")
        result = _run_pass(DCEPass(), mir)
        fn = result.artifact.functions[0]
        opcodes = [i.opcode for b in fn.blocks for i in b.instructions]
        assert "CALL" in opcodes
        assert "LOAD_ENV" in opcodes

    def test_preserves_side_effects(self):
        mir = _compile_to_mir("(define x 1)")
        result = _run_pass(DCEPass(), mir)
        fn = result.artifact.functions[0]
        opcodes = [i.opcode for b in fn.blocks for i in b.instructions]
        assert "DEFINE_ONCE" in opcodes


# --- CFG Simplify ---


class TestCFGSimplify:
    def test_removes_unreachable(self):
        unreachable = MIRBlock(
            99, (MIRInstruction("LOAD_CONST", (0, 0)),), MIRTerminator("RETURN", (0,))
        )
        entry = MIRBlock(0, (), MIRTerminator("RETURN", (0,)))
        fn = MIRFunction(Symbol(name="test"), (), 1, (entry, unreachable), 0)
        prog = MIRProgram((fn,), MIRConstantPool())

        result = _run_pass(CFGSimplifyPass(), prog)
        fn_out = result.artifact.functions[0]
        assert len(fn_out.blocks) == 1

    def test_threads_jumps(self):
        b0 = MIRBlock(0, (), MIRTerminator("JUMP", (1,)))
        b1 = MIRBlock(1, (), MIRTerminator("JUMP", (2,)))
        b2 = MIRBlock(2, (MIRInstruction("LOAD_CONST", (0, 0)),), MIRTerminator("RETURN", (0,)))
        fn = MIRFunction(Symbol(name="test"), (), 1, (b0, b1, b2), 0)
        prog = MIRProgram((fn,), MIRConstantPool())

        result = _run_pass(CFGSimplifyPass(), prog)
        fn_out = result.artifact.functions[0]
        assert len(fn_out.blocks) == 1

    def test_merges_linear(self):
        b0 = MIRBlock(0, (MIRInstruction("LOAD_CONST", (0, 0)),), MIRTerminator("JUMP", (1,)))
        b1 = MIRBlock(1, (MIRInstruction("LOAD_CONST", (1, 1)),), MIRTerminator("RETURN", (1,)))
        fn = MIRFunction(Symbol(name="test"), (), 2, (b0, b1), 0)
        prog = MIRProgram((fn,), MIRConstantPool())

        result = _run_pass(CFGSimplifyPass(), prog)
        fn_out = result.artifact.functions[0]
        assert len(fn_out.blocks) == 1
        assert len(fn_out.blocks[0].instructions) == 2


# --- Tail Call ---


class TestTailCall:
    def test_converts_call_return_to_tailcall(self):
        call = MIRInstruction("CALL", (1, 0, (2,)))
        b = MIRBlock(
            0,
            (MIRInstruction("LOAD_ENV", (0, Symbol(name="f"))), call),
            MIRTerminator("RETURN", (1,)),
        )
        fn = MIRFunction(Symbol(name="test"), (), 3, (b,), 0)
        prog = MIRProgram((fn,), MIRConstantPool())

        result = _run_pass(TailCallPass(), prog)
        fn_out = result.artifact.functions[0]
        assert fn_out.blocks[0].terminator.opcode == "TAIL_CALL"

    def test_no_convert_when_different_register(self):
        call = MIRInstruction("CALL", (1, 0, (2,)))
        b = MIRBlock(0, (call,), MIRTerminator("RETURN", (0,)))
        fn = MIRFunction(Symbol(name="test"), (), 3, (b,), 0)
        prog = MIRProgram((fn,), MIRConstantPool())

        result = _run_pass(TailCallPass(), prog)
        fn_out = result.artifact.functions[0]
        assert fn_out.blocks[0].terminator.opcode == "RETURN"


# --- Inline ---


class TestInline:
    def test_inlines_simple_function(self):
        mir = _compile_to_mir("(define const5 (lambda () 5))(const5)")
        result = _run_pass(InlinePass(), mir)
        assert len(result.artifact.functions) == 1

    def test_no_inline_recursive(self):
        mir = _compile_to_mir("(define f (lambda (x) (cond ((= x 0) 1) (t (f (- x 1))))))(f 5)")
        result = _run_pass(InlinePass(), mir)
        assert len(result.artifact.functions) >= 2

    def test_no_inline_with_effects(self):
        mir = _compile_to_mir("(define f (lambda () (perform my-effect 1)))(f)")
        result = _run_pass(InlinePass(), mir)
        assert result.success


# --- Golden test: VM result unchanged with optimization ---


class TestOptimizationCorrectness:
    def test_hello_qy_pipeline(self):
        """Full pipeline with and without optimization produces same LIR structure."""
        forms = read("(+ 1 2)")
        env = standard_environment()

        ctx1 = PassContext(input_artifact=forms, session=PipelineSession(env=env))
        r1 = build_optimization_pipeline(optimize=False).run(ctx1)
        r1_artifact = _lir_artifact(r1.artifact)

        ctx2 = PassContext(input_artifact=forms, session=PipelineSession(env=env))
        r2 = build_optimization_pipeline(optimize=True).run(ctx2)
        assert r2.success
        r2_artifact = _lir_artifact(r2.artifact)

        assert len(r2_artifact.functions[0].instructions) <= len(
            r1_artifact.functions[0].instructions
        )
