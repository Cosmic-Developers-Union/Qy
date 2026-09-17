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
from qy.core.syntax import Symbol
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


def test_rg_sees_every_tracked_qy_source_file():
    """`rg`（以及同用 ignore crate 的工具）必须能看到全部已跟踪源码。.

    `.gitignore` 里未锚定的通用目录规则（例如裸 `instance/`）会连带匹配
    `qy/vm/instance/`。git 自身对被跟踪文件不判 ignore，但 ripgrep 在递归遍历时
    会**静默跳过**该目录整个子树，导致 grep 类审计漏掉真实代码。这里直接以
    `rg --files` 的可见文件集为准做守卫。
    """
    import pathlib
    import shutil
    import subprocess

    if shutil.which("rg") is None:
        import pytest

        pytest.skip("ripgrep is not installed")

    repo_root = pathlib.Path(__file__).resolve().parent.parent
    tracked = {
        path
        for path in subprocess.run(
            ["git", "ls-files", "qy"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.split()
        if path.endswith(".py")
    }
    visible = set(
        subprocess.run(
            ["rg", "--files", "qy"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.split()
    )

    missing = sorted(tracked - visible)
    assert missing == [], f"rg cannot see tracked qy sources: {missing}"


def test_repo_root_toolchain_files_are_not_git_ignored():
    """仓库根的工具链文件不得被 .gitignore 规则连带匹配。.

    实例：`*.mod*`（内核模块编译产物）会连带匹配 `go.mod`，导致 Go module 文件被静默
    忽略、无法提交（且 rg 也可能跳过）。这里用 `rg --files` 的可见性做守卫。
    """
    import pathlib
    import shutil
    import subprocess

    if shutil.which("rg") is None:
        import pytest

        pytest.skip("ripgrep is not installed")

    repo_root = pathlib.Path(__file__).resolve().parent.parent
    required = ("go.mod", "pyproject.toml", "package.json", "Makefile")
    visible = set(
        subprocess.run(
            ["rg", "--files"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.split()
    )

    missing = [name for name in required if name not in visible]
    assert missing == [], f"toolchain files invisible to rg (git-ignored?): {missing}"
