from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from qy.evaluator import evaluate_file
from qy.reader import Symbol

S = Symbol


def test_example_code001():
    path = Path("examples/codes/code001.qy")
    result = evaluate_file(path)

    assert isinstance(result, float)
    assert result == pytest.approx(51926.26973684211)


def test_evaluate_file_runs_program_and_returns_last_value():
    with TemporaryDirectory() as temp_dir:
        path = Path(temp_dir) / "program.qy"
        path.write_text(
            """
            (from qy.str import str-upper as upper)
            (upper "qy")
            """,
            encoding="utf-8",
        )

        assert evaluate_file(path) == S("QY")
