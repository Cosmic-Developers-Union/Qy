from pathlib import Path

from qy.evaluator import evaluate_file

ROOT = Path(__file__).resolve().parent.parent

print(evaluate_file(ROOT / "examples/codes/code001.qy"))
