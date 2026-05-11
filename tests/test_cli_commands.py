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
    result = runner.invoke(app, ["examples/codes/code001.qy"])

    assert result.exit_code == 0, result.output
    assert "51926.26973684211" in result.output


def test_check_command(runner, app):
    result = runner.invoke(app, ["check", "examples/codes/code001.qy"])

    assert result.exit_code == 0, result.output
    assert "ok" in result.output


def test_fmt_command(runner, app):
    result = runner.invoke(app, ["fmt", "examples/codes/code001.qy"])

    assert result.exit_code == 0, result.output
    assert "(+" in result.output
    assert "(* 123 456)" in result.output


def test_ast_command(runner, app):
    result = runner.invoke(app, ["ast", "examples/codes/code001.qy"])

    assert result.exit_code == 0, result.output
    assert "Symbol('+')" in result.output


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
