# coding: utf-8
"""Tests for pass infrastructure and optimization passes."""

from __future__ import annotations

from typing import Any
from typing import cast

from qy.build.pipeline import bytecode_artifact
from qy.core.syntax import Symbol
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
from qy.sem.core import IntValue
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

    def test_optimized_pipeline_folds_literal_arithmetic(self):
        """const_prop 把字面量拼写降成常量后，const_fold 可整体折叠 (+ 1 2)。."""
        forms = read("(+ 1 2)")
        env = standard_environment()
        ctx = PassContext(input_artifact=forms, session=PipelineSession(env=env))
        result = build_optimization_pipeline(optimize=True).run(ctx)
        assert result.success
        artifact = _lir_artifact(result.artifact)
        fn = artifact.functions[0]
        opcodes = [i.opcode for i in fn.instructions]
        assert "CALL" not in opcodes
        assert any("CONST" in opcode or opcode == "LOAD_HOST" for opcode in opcodes)

    def test_optimized_pipeline_respects_shadowed_operator(self):
        """被 let/define shadow 的算子名不得折叠成内置算子（历史误编译）。."""
        from qy.async_utils import run_coro
        from qy.build.pipeline import compile_source_to_bytecode
        from qy.session.runtime_space import create_standard_runtime_space
        from qy.vm.instance.machine import RegisterVirtualMachine

        source = "(let ((+ (lambda (left right) 0))) (+ 41 1))"
        env = create_standard_runtime_space()
        result = compile_source_to_bytecode(
            source,
            PipelineSession(env=env),
            options=PipelineOptions(error_threshold=10**6, optimize=True),
        )
        assert not [d for d in result.diagnostics if d.severity == "error"]
        bytecode = bytecode_artifact(result)
        outcome = run_coro(RegisterVirtualMachine(bytecode, env).evaluate_program())

        assert outcome == [IntValue(0)]

    def test_optimized_pipeline_respects_shadowed_literal(self):
        from qy.async_utils import run_coro
        from qy.build.pipeline import compile_source_to_bytecode
        from qy.session.runtime_space import create_standard_runtime_space
        from qy.vm.instance.machine import RegisterVirtualMachine

        env = create_standard_runtime_space()
        result = compile_source_to_bytecode(
            "(define 2 3) 2",
            PipelineSession(env=env),
            options=PipelineOptions(error_threshold=10**6, optimize=True),
        )
        bytecode = bytecode_artifact(result)
        outcome = run_coro(RegisterVirtualMachine(bytecode, env).evaluate_program())

        assert outcome == [IntValue(3), IntValue(3)]

    def test_optimization_preserves_symbol_space_layout(self):
        """优化 pass 不得丢弃 HIR 下沉的 layout 事实。."""
        from qy.build.pipeline import compile_source_to_bytecode

        env = standard_environment()
        result = compile_source_to_bytecode(
            "(define x 1) (+ x 1)",
            PipelineSession(env=env),
            options=PipelineOptions(error_threshold=10**6, optimize=True),
        )
        bytecode = bytecode_artifact(result)

        assert bytecode.symbol_spaces
        assert any(
            slot.symbol.name == "x" for layout in bytecode.symbol_spaces for slot in layout.slots
        )


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


# ---------------------------------------------------------------------------
# 默认管线接线（PipelineOptions.optimize）
# ---------------------------------------------------------------------------


def test_optimize_is_off_by_default():
    assert PipelineOptions().optimize is False


def test_default_pipeline_includes_optimize_slot():
    from qy.build.pipeline import build_default_pipeline

    names = [p.name for p in build_default_pipeline().passes]
    assert "optimize.mir" in names
    assert names.index("mir.validate") < names.index("optimize.mir") < names.index("lir.lower")


def test_optimize_mir_is_noop_when_disabled():
    from qy.passes.optimize.apply import OptimizeMIRPass

    program = _compile_to_mir("(+ 1 2)")
    result = OptimizeMIRPass().run(
        PassContext(
            input_artifact=program,
            artifact_kind="mir",
            session=PipelineSession.minimal(),
            options=PipelineOptions(),
        )
    )

    assert result.artifact is program
    assert result.diagnostics == ()


def test_optimize_mir_runs_when_enabled():
    from qy.passes.optimize.apply import OptimizeMIRPass

    program = _compile_to_mir("(+ 1 2)")
    result = OptimizeMIRPass().run(
        PassContext(
            input_artifact=program,
            artifact_kind="mir",
            session=PipelineSession.minimal(),
            options=PipelineOptions(error_threshold=10**6, optimize=True),
        )
    )

    assert result.artifact is not None


# ---------------------------------------------------------------------------
# 优化正确性回归（本轮修复的缺陷）
# ---------------------------------------------------------------------------


def test_terminator_targets_include_effect_resume_edge():
    """EFFECT_PERFORM 的 resume 块是 CFG 后继，不能当作不可达。."""
    from qy.ir.mir import terminator_target_positions
    from qy.ir.mir import terminator_targets

    term = MIRTerminator("EFFECT_PERFORM", (1, Symbol("ask"), 2, 7, True))

    assert terminator_targets(term) == [7]
    assert terminator_target_positions(term) == (3,)


def test_cfg_simplify_keeps_effect_resume_block():
    """cfg_simplify 不得删掉 perform 的 resume 块。."""
    import qy.passes.optimize.apply as apply_mod
    from qy.async_utils import run_coro
    from qy.build.pipeline import compile_source_to_bytecode
    from qy.passes.optimize.apply import OPTIMIZE_PASSES
    from qy.session.runtime_space import create_standard_runtime_space
    from qy.vm.instance.machine import RegisterVirtualMachine

    source = """
    (defeffect ask)
    (handle (+ 1 (perform ask 41)) ((ask (arg k) (resume k arg))))
    """
    original = apply_mod.OPTIMIZE_PASSES
    apply_mod.OPTIMIZE_PASSES = tuple(f for i, f in enumerate(OPTIMIZE_PASSES) if i < 11)
    try:
        env = create_standard_runtime_space()
        result = compile_source_to_bytecode(
            source,
            PipelineSession(env=env),
            options=PipelineOptions(error_threshold=10**6, optimize=True),
        )
        assert not [d for d in result.diagnostics if d.severity == "error"]
        outcome = run_coro(
            RegisterVirtualMachine(bytecode_artifact(result), env).evaluate_program()
        )
    finally:
        apply_mod.OPTIMIZE_PASSES = original

    assert outcome[-1] == IntValue(42)


def test_liveness_counts_terminator_register_uses():
    """只在 terminator 中被读取的寄存器必须进入 live_out。."""
    from qy.analysis.liveness import compute_liveness
    from qy.ir.mir import MIRBlock
    from qy.ir.mir import MIRFunction
    from qy.ir.mir import MIRTerminator

    # (tail-call f a b)：a、b 只在 terminator 中被读取
    function = MIRFunction(
        Symbol("g"),
        (),
        3,
        (
            MIRBlock(
                0,
                (
                    MIRInstruction("LOAD_ENV", (0, Symbol("f"))),
                    MIRInstruction("LOAD_ENV", (1, Symbol("a"))),
                    MIRInstruction("LOAD_ENV", (2, Symbol("b"))),
                ),
                MIRTerminator("TAIL_CALL", (0, (1, 2))),
            ),
        ),
        0,
    )
    info = compute_liveness(function)

    # 这三个寄存器只在 terminator 中被读取，必须出现在块末尾的 live_out 中
    assert {0, 1, 2} <= set(info.live_out[0])


def test_register_allocation_keeps_simultaneously_live_registers_apart():
    """只在 TAIL_CALL 中被读取的寄存器不得被复用成同一物理寄存器。."""
    from qy.passes.optimize.reg_alloc import RegisterAllocationPass

    mir = _compile_to_mir("(defun f (a b) (+ a b))")
    result = _run_pass(RegisterAllocationPass(), mir)
    target = _mir_artifact(result.artifact)
    function = next(fn for fn in target.functions if fn.name.name == "f")
    tail = function.blocks[0].terminator

    assert tail.opcode == "TAIL_CALL"
    arg_regs = tail.operands[1]
    assert isinstance(arg_regs, tuple)
    assert len({tail.operands[0], *arg_regs}) == 3


def test_register_allocation_preserves_nested_let_semantics():
    """回归：reg_alloc 曾把 let 内经 TAIL_CALL 使用的值合并到同一寄存器。."""
    from qy.async_utils import run_coro
    from qy.build.pipeline import compile_source_to_bytecode
    from qy.session.runtime_space import create_standard_runtime_space
    from qy.vm.instance.machine import RegisterVirtualMachine

    env = create_standard_runtime_space()
    result = compile_source_to_bytecode(
        "(defun g (x) (let ((y (+ x 1))) (* y 2))) (g 5)",
        PipelineSession(env=env),
        options=PipelineOptions(error_threshold=10**6, optimize=True),
    )
    outcome = run_coro(RegisterVirtualMachine(bytecode_artifact(result), env).evaluate_program())

    assert outcome[-1] == IntValue(12)


def test_intern_does_not_merge_identity_observable_constants():
    """字符串/符号的 identity 目前可观察（= 按 identity 比较），不得合并。."""
    from qy.core.syntax import Symbol as QySymbol
    from qy.passes.optimize.intern import _intern_key
    from qy.sem.core import StringValue

    assert _intern_key(StringValue("a")) is None
    assert _intern_key(QySymbol("a")) is None


def test_intern_key_distinguishes_t_and_none():
    """T 与 none 都是空 frozen dataclass，hash 相同但语义不同。."""
    from qy.core.syntax import NONE
    from qy.core.syntax import T
    from qy.passes.optimize.intern import _intern_key

    assert _intern_key(T) != _intern_key(NONE)


def test_effect_resume_exposes_all_three_register_operands():
    """EFFECT_RESUME(dst, cont, value) 三个操作数都是寄存器。."""
    from qy.ir.mir import register_def_position
    from qy.ir.mir import register_operand_positions

    inst = MIRInstruction("EFFECT_RESUME", (5, 0, 4))

    assert register_operand_positions(inst) == (0, 1, 2)
    assert register_def_position(inst) == 0


def test_reg_alloc_remaps_effect_resume_value_register():
    """回归：value 寄存器漏重映射会让 resume 传回旧寄存器里的值。."""
    source = """
    (defeffect ping)
    (handle (perform ping 42) ((ping (v k) (resume k (+ v 8)))))
    """
    from qy.async_utils import run_coro
    from qy.build.pipeline import compile_source_to_bytecode
    from qy.session.runtime_space import create_standard_runtime_space
    from qy.vm.instance.machine import RegisterVirtualMachine

    env = create_standard_runtime_space()
    result = compile_source_to_bytecode(
        source,
        PipelineSession(env=env),
        options=PipelineOptions(error_threshold=10**6, optimize=True),
    )
    assert not [d for d in result.diagnostics if d.severity == "error"]
    outcome = run_coro(RegisterVirtualMachine(bytecode_artifact(result), env).evaluate_program())

    assert outcome[-1] == IntValue(50)


def test_effect_multi_handle_under_full_optimization():
    """回归：两个 handle + resume 的算术结果在全量优化下必须保持一致。."""
    source = """
    (defeffect ask)
    (handle (perform ask 7) ((ask (x k) (resume k (+ x 35)))))
    (handle (+ 1 (perform ask 10)) ((ask (v k) (resume k (* v 3)))))
    """
    from qy.async_utils import run_coro
    from qy.build.pipeline import compile_source_to_bytecode
    from qy.session.runtime_space import create_standard_runtime_space
    from qy.vm.instance.machine import RegisterVirtualMachine

    env = create_standard_runtime_space()
    result = compile_source_to_bytecode(
        source,
        PipelineSession(env=env),
        options=PipelineOptions(error_threshold=10**6, optimize=True),
    )
    outcome = run_coro(RegisterVirtualMachine(bytecode_artifact(result), env).evaluate_program())

    assert outcome[-2:] == [IntValue(42), IntValue(31)]
