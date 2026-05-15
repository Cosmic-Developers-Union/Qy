import pytest

pytest.importorskip("typer")

from typer.testing import CliRunner

from qy.cli import create_app


def test_qytest_runner_executes_qy_suite():
    runner = CliRunner()
    app = create_app()

    result = runner.invoke(app, ["run", "test.qy", "tests/qy"])

    assert result.exit_code == 0, result.output
    assert "qytest-summary" in result.output
    assert "failed= 0" in result.output
    assert "true" in result.output
