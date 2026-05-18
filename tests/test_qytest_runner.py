import subprocess

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
    assert "T" in result.output


def test_qytest_cli_entry_point():
    """Verify `python -m qy test.qy tests/qy` works as a real subprocess."""
    import sys

    result = subprocess.run(
        [sys.executable, "-m", "qy", "test.qy", "tests/qy"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, f"stdout: {result.stdout}\nstderr: {result.stderr}"
    assert "qytest-pass" in result.stdout
    assert "qytest-summary" in result.stdout
    assert "failed= 0" in result.stdout
