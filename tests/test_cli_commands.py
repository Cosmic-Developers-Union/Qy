import pytest
from click.testing import CliRunner

from qy.cli import create_app


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def app():
    return create_app()


def test_evaluates_target_file(runner, app):
    result = runner.invoke(app, ["run", "examples/qy/validation/00_host_arithmetic.qy"])

    assert result.exit_code == 0, result.output
    assert "42" in result.output


def test_check_command(runner, app):
    result = runner.invoke(app, ["check", "examples/qy/validation/00_host_arithmetic.qy"])

    assert result.exit_code == 0, result.output
    assert "ok" in result.output


def test_fmt_command(runner, app):
    result = runner.invoke(app, ["fmt", "examples/qy/validation/00_host_arithmetic.qy"])

    assert result.exit_code == 0, result.output
    assert "(+" in result.output
    assert "(* 6 7)" in result.output


def test_fmt_command_with_write_flag(runner, app, tmp_path):
    test_file = tmp_path / "test.qy"
    test_file.write_text("(+   1   2)\n")

    result = runner.invoke(app, ["fmt", "-w", str(test_file)])

    assert result.exit_code == 0, result.output
    assert "formatted" in result.output
    assert test_file.read_text() == "(+ 1 2)\n"


def test_fmt_command_with_syntax_error(runner, app, tmp_path):
    test_file = tmp_path / "invalid.qy"
    test_file.write_text("(+ 1 2\n")  # Missing closing paren

    result = runner.invoke(app, ["fmt", str(test_file)])

    assert result.exit_code == 1
    assert "syntax error" in result.output


def test_ast_command(runner, app):
    result = runner.invoke(app, ["ast", "examples/qy/validation/00_host_arithmetic.qy"])

    assert result.exit_code == 0, result.output
    assert "Symbol('+')" in result.output


@pytest.mark.parametrize(
    ("command", "expected"),
    (
        ("expand", "Symbol('+')"),
        ("hir", "ProgramIR("),
        ("mir", "fn#0 <main>() entry=bb0"),
        ("bytecode", "fn#0 <main>() regs="),
    ),
)
def test_pipeline_debug_commands_support_stdin(runner, app, command, expected):
    result = runner.invoke(app, [command, "-"], input="(+ 1 2)\n")

    assert result.exit_code == 0, result.output
    assert expected in result.output


def test_expand_command_dumps_runtime_atom_macro_result(runner, app):
    result = runner.invoke(app, ["expand", "-"], input="(macro one () (+ 0 1))\n(one)\n")

    assert result.exit_code == 0, result.output
    assert "IntValue(value=1)" in result.output


def test_pipeline_debug_commands_return_nonzero_on_diagnostics(runner, app):
    result = runner.invoke(app, ["hir", "-"], input="(+ 1\n")

    assert result.exit_code == 1
    assert "error:" in result.output


@pytest.mark.parametrize("command", ("hir", "mir", "lir", "bytecode", "wasm", "llvm", "export"))
def test_debug_commands_do_not_cascade_lir_errors(runner, app, command):
    """未解析符号只报该 HIR 诊断，不得级联出 "LIR main function index ... out of range"。."""
    result = runner.invoke(app, [command, "-"], input="(nonexistent-op 1)\n")

    assert result.exit_code == 1, (command, result.output)
    assert "unresolved symbol 'nonexistent-op'" in result.output, command
    assert "out of range for 0 LIR functions" not in result.output, command


def test_operators_command(runner, app):
    result = runner.invoke(app, ["operators"])

    assert result.exit_code == 0, result.output
    assert "## 内建算子" in result.output
    assert "模块：`qy.core`" in result.output
    assert "## 模块 qy.io" in result.output
    assert "`print`" in result.output
    assert "`list`" in result.output


@pytest.mark.parametrize(
    ("command", "expected"),
    (
        ("ast", "Symbol('+')"),
        ("run", "3"),
        ("fmt", "(+ 1 2)"),
        ("check", "<stdin>: ok"),
    ),
)
def test_path_commands_support_stdin(runner, app, command, expected):
    result = runner.invoke(app, [command, "-"], input="(+ 1 2)\n")

    assert result.exit_code == 0, result.output
    assert expected in result.output


def test_fmt_refuses_write_to_stdin(runner, app):
    result = runner.invoke(app, ["fmt", "-w", "-"], input="(+ 1 2)\n")

    assert result.exit_code == 2
    assert "cannot --write to stdin" in result.output


def test_missing_file_is_reported_without_traceback(runner, app):
    result = runner.invoke(app, ["ast", "does-not-exist.qy"])

    assert result.exit_code == 1
    assert "Traceback" not in result.output


def test_unknown_option_is_reported_without_traceback(runner, app):
    result = runner.invoke(app, ["ast", "--bogus"])

    assert result.exit_code == 2
    assert "Traceback" not in result.output
    assert "No such option" in result.output


def test_completion_lists_every_registered_command(runner, app):
    result = runner.invoke(app, ["completion", "sh"])

    assert result.exit_code == 0, result.output
    for name in app.commands:
        assert name in result.output
