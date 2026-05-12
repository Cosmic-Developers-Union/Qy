from qy import MIRProgram
from qy import dump_mir
from qy import lower_mir
from qy.ir import CallExpr
from qy.ir import CondExpr
from qy.ir import DefunExpr
from qy.lowering import lower_source


def test_mir_lowering_emits_cfg_blocks_for_cond():
    hir = lower_source("(cond (true 1) (false 2))")

    mir = lower_mir(hir)

    assert isinstance(mir, MIRProgram)
    assert mir.ok
    main = mir.functions[mir.main]
    assert len(main.blocks) > 1
    assert any(block.terminator.opcode == "BRANCH" for block in main.blocks)


def test_mir_lowering_preserves_tail_call_as_terminator():
    hir = lower_source(
        """
        (defun sum-to (n acc)
          (cond
            ((eq n 0) acc)
            (true (sum-to (- n 1) (+ acc n)))))
        """
    )
    definition = hir.body[0]
    assert isinstance(definition, DefunExpr)
    cond = definition.body[0]
    assert isinstance(cond, CondExpr)
    recursive_call = cond.clauses[1].result
    assert isinstance(recursive_call, CallExpr)
    assert recursive_call.tail_position

    mir = lower_mir(hir)
    sum_to = next(function for function in mir.functions if function.name.name == "sum-to")

    assert any(block.terminator.opcode == "TAIL_CALL" for block in sum_to.blocks)


def test_mir_lowering_keeps_top_level_results():
    hir = lower_source("(+ 1 2)\n(+ 3 4)")

    mir = lower_mir(hir)
    main = mir.functions[mir.main]

    assert (
        sum(
            1
            for block in main.blocks
            for instruction in block.instructions
            if instruction.opcode == "APPEND_RESULT"
        )
        == 2
    )


def test_mir_dump_formats_cfg_and_scope_information():
    hir = lower_source("(let ((x 1)) (cond (x (+ x 1)) (true 0)))")

    mir = lower_mir(hir)
    rendered = dump_mir(mir)

    assert "fn#0 <main>() entry=bb0 regs=" in rendered
    assert "ENTER_SCOPE" in rendered
    assert "EXIT_SCOPE" in rendered
    assert "BRANCH r" in rendered
    assert "APPEND_RESULT r" in rendered


def test_mir_dump_shows_lambda_and_macro_construction():
    hir = lower_source(
        """
        (let ((inc (lambda (x) (+ x 1))))
          (macro twice (form) (cons '+ (cons form (cons form '()))))
          inc)
        """
    )

    mir = lower_mir(hir)
    rendered = dump_mir(mir)

    assert "MAKE_FUNCTION fn#" in rendered
    assert "MAKE_MACRO twice" in rendered
    assert "STORE_LOCAL inc, r" in rendered
    assert "STORE_LOCAL twice, r" in rendered


def test_mir_dump_shows_tail_call_terminator():
    hir = lower_source(
        """
        (defun sum-to (n acc)
          (cond
            ((eq n 0) acc)
            (true (sum-to (- n 1) (+ acc n)))))
        """
    )

    mir = lower_mir(hir)
    rendered = dump_mir(mir)

    assert "TAIL_CALL r" in rendered
