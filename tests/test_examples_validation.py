from examples.run_validation import CASES
from examples.run_validation import ROOT
from examples.run_validation import run_case
from qy.reader import read


def test_validation_examples_run():
    for case in CASES:
        run_case(case)


def test_design_examples_are_parseable():
    for path in sorted((ROOT / "design").glob("*.qy")):
        read(path.read_text(encoding="utf-8"), source_name=str(path))
