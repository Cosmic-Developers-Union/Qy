# coding: utf-8

from qy.backend.vm.compiler import compile_lir_bytecode
from qy.backend.vm.spec import OPCODE_TABLE
from qy.backend.vm.spec import AbstractVMState
from qy.backend.vm.spec import CallConvention
from qy.backend.vm.spec import ContinuationSpec
from qy.backend.vm.spec import FrameLayout
from qy.backend.vm.spec import HandlerSpec
from qy.backend.vm.spec import RegisterAllocation
from qy.backend.vm.spec import VMState
from qy.frontend.reader import Symbol
from qy.ir.lir import LIRFunction
from qy.ir.lir import LIRInstruction
from qy.ir.lir import LIRProgram
from qy.ir.mir import MIRBlock
from qy.ir.mir import MIRFunction
from qy.ir.mir import MIRProgram
from qy.ir.mir import MIRTerminator
from qy.passes.lir.verify import VerifyLIRPass
from qy.passes.mir.validate import ValidateMIRPass
from qy.passes.pass_base import PassContext


def test_vm_spec_exports_contract_metadata_without_instance_state():
    assert OPCODE_TABLE["CALL"].has_dest is True
    assert OPCODE_TABLE["RETURN"].is_terminator is True
    assert CallConvention().tail_call_eligible is True
    assert FrameLayout(register_count=3).register_count == 3
    assert RegisterAllocation(0, 2, 2, 4, 6).total_count == 6
    assert HandlerSpec("ask", 1).effect_name == "ask"
    assert ContinuationSpec().scope_stack is True
    assert AbstractVMState(pc=0, register_count=2, scope_depth=0, handler_depth=0).pc == 0
    assert VMState.READY.value == "ready"


def test_mir_validate_pass_reports_structural_errors():
    program = MIRProgram(
        (
            MIRFunction(
                Symbol("broken"),
                (),
                1,
                (MIRBlock(0, (), MIRTerminator("JUMP", (99,))),),
            ),
        )
    )

    result = ValidateMIRPass().run(PassContext(input_artifact=program, artifact_kind="mir"))

    assert result.success is False
    assert any("jumps to missing block bb99" in d.message for d in result.diagnostics)


def test_lir_verify_pass_reports_register_errors():
    program = LIRProgram(
        (
            LIRFunction(
                Symbol("broken"),
                (),
                1,
                (
                    LIRInstruction("LOAD_HOST", (2, 42)),
                    LIRInstruction("RETURN", (0,)),
                ),
            ),
        )
    )

    result = VerifyLIRPass().run(PassContext(input_artifact=program, artifact_kind="lir"))

    assert result.success is False
    assert any("out-of-range register r2" in d.message for d in result.diagnostics)


def test_vm_bytecode_emit_rejects_abstract_machine_lir_opcode():
    program = LIRProgram(
        (
            LIRFunction(
                Symbol("abstract"),
                (),
                1,
                (
                    LIRInstruction("FRAME_ENTER", ()),
                    LIRInstruction("RETURN", (0,)),
                ),
            ),
        ),
        dialect="compat",
    )

    bytecode = compile_lir_bytecode(program)

    assert not bytecode.ok
    assert bytecode.functions == ()
    assert any(
        "cannot be emitted to register VM bytecode" in d.message for d in bytecode.diagnostics
    )
