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


def test_completion_command_outputs_bash_script(runner, app):
    result = runner.invoke(app, ["completion", "bash"])

    assert result.exit_code == 0, result.output
    assert "complete -o default" in result.output
    assert "mir" in result.output
    assert "operators" in result.output


def test_completion_command_outputs_zsh_script(runner, app):
    result = runner.invoke(app, ["completion", "zsh"])

    assert result.exit_code == 0, result.output
    assert "#compdef qy" in result.output
    assert "compdef _qy qy" in result.output


def test_completion_command_outputs_sh_helper(runner, app):
    result = runner.invoke(app, ["completion", "sh"])

    assert result.exit_code == 0, result.output
    assert "qy_completion_commands" in result.output
