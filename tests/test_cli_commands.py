import pytest

pytest.importorskip("typer")

from typer.testing import CliRunner

from qy.cli import create_app


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def app():
    return create_app()


def test_evaluates_target_file(runner, app):
    result = runner.invoke(app, ["examples/validation/00_host_arithmetic.qy"])

    assert result.exit_code == 0, result.output
    assert "42" in result.output


def test_check_command(runner, app):
    result = runner.invoke(app, ["check", "examples/validation/00_host_arithmetic.qy"])

    assert result.exit_code == 0, result.output
    assert "ok" in result.output


def test_fmt_command(runner, app):
    result = runner.invoke(app, ["fmt", "examples/validation/00_host_arithmetic.qy"])

    assert result.exit_code == 0, result.output
    assert "(+" in result.output
    assert "(* 6 7)" in result.output


def test_ast_command(runner, app):
    result = runner.invoke(app, ["ast", "examples/validation/00_host_arithmetic.qy"])

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


def test_pipeline_debug_commands_return_nonzero_on_diagnostics(runner, app):
    result = runner.invoke(app, ["hir", "-"], input="(+ 1\n")

    assert result.exit_code == 1
    assert "error:" in result.output


def test_operators_command(runner, app):
    result = runner.invoke(app, ["operators"])

    assert result.exit_code == 0, result.output
    assert "## 内建算子" in result.output
    assert "模块：`qy.core`" in result.output
    assert "`py` - Effect 算子" in result.output
    assert "## 模块 qy.io" in result.output
    assert "`print`" in result.output
    assert "## 模块 qy.str" in result.output
    assert "`str-upper`" in result.output
