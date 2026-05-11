import pytest

pytest.importorskip("typer")

from typer.testing import CliRunner

from qy.cli import _repl_completions
from qy.cli import create_app
from qy.runtime import Qy


def test_repl_keeps_session_environment():
    runner = CliRunner()
    app = create_app()

    result = runner.invoke(
        app,
        input="(defun square (x) (* x x))\n(square 12)\n.exit\n",
    )

    assert result.exit_code == 0, result.output
    assert "144" in result.output


def test_repl_completions_include_commands_and_symbols():
    completions = _repl_completions(Qy(), ".he")
    assert ".help" in completions

    completions = _repl_completions(Qy(), "def")
    assert "defun" in completions
