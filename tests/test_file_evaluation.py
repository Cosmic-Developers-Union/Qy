from pathlib import Path
from tempfile import TemporaryDirectory

from qy.evaluator import evaluate_file
from qy.reader import Symbol

S = Symbol


def test_validation_example_file():
    path = Path("examples/validation/00_host_arithmetic.qy")
    result = evaluate_file(path)

    assert result == 42


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
