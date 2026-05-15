# coding: utf-8
# ruff: noqa: I001

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from qy.display import format_value
from qy.runtime import Qy


ROOT = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Case:
    path: str
    expected: str


CASES = (
    Case("validation/00_host_arithmetic.qy", "42"),
    Case("validation/01_quote_chain.qy", "(alpha beta gamma)"),
    Case("validation/02_symbol_space_let.qy", "42"),
    Case("validation/03_functions_tail_call.qy", "45150"),
    Case("validation/04_macro_hygiene.qy", "(99 42 0)"),
    Case("validation/05_effect_resume.qy", "42"),
    Case("validation/06_parallel_effects.qy", "(2 40)"),
    Case("validation/07_module_import.qy", "42"),
    Case("validation/08_host_interop.qy", "42"),
    Case("validation/09_register_vm_tail_call.qy", "2001000"),
)


def run_case(case: Case) -> None:
    path = ROOT / case.path
    qy = Qy()
    result = qy.evaluate_file(path)
    formatted = format_value(result)
    if formatted != case.expected:
        raise AssertionError(f"{case.path}: expected {case.expected!r}, got {formatted!r}")
    print(f"[ok] {case.path} -> {formatted}")


def main() -> int:
    for case in CASES:
        run_case(case)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
