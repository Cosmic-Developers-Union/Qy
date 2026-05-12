# coding: utf-8

from __future__ import annotations

import argparse
import json
import statistics
import time
from collections.abc import Callable
from dataclasses import asdict
from dataclasses import dataclass
from typing import Literal

from qy.evaluator import Environment
from qy.evaluator import run_async
from qy.ir import ProgramIR
from qy.ir_vm import IRVirtualMachine
from qy.lowering import lower
from qy.macroexpand import macroexpand
from qy.reader import read
from qy.runtime import Qy

__all__ = [
    "DEFAULT_CASES",
    "BenchmarkCase",
    "BenchmarkPhase",
    "BenchmarkResult",
    "run_benchmarks",
]

BenchmarkPhase = Literal["source", "lower", "ir"]


@dataclass(frozen=True, slots=True)
class BenchmarkCase:
    name: str
    source: str
    setup_source: str = ""
    iterations: int = 1_000


@dataclass(frozen=True, slots=True)
class BenchmarkResult:
    case: str
    phase: BenchmarkPhase
    iterations: int
    repeat: int
    best_seconds: float
    mean_seconds: float
    median_seconds: float
    ops_per_second: float
    seconds_per_iteration: float


DEFAULT_CASES: tuple[BenchmarkCase, ...] = (
    BenchmarkCase(
        "arithmetic",
        "(+ 1 2 3 4 5 6 7 8 9 10)",
        iterations=1_000,
    ),
    BenchmarkCase(
        "nested-calls",
        "(* (+ 1 2) (- 10 3) (/ 20 2))",
        iterations=800,
    ),
    BenchmarkCase(
        "tail-recursion",
        "(sum-to 300 0)",
        setup_source="""
        (defun sum-to (n acc)
          (cond
            ((eq n 0) acc)
            (true (sum-to (- n 1) (+ acc n)))))
        """,
        iterations=80,
    ),
    BenchmarkCase(
        "macro-call",
        "(twice (+ 1 2))",
        setup_source="(macro twice (form) (cons '+ (cons form (cons form '()))))",
        iterations=500,
    ),
    BenchmarkCase(
        "effect-resume",
        """
        (handle
          (+ 1 (perform ask 41))
          ((ask (arg k) (resume k arg))))
        """,
        setup_source="(defeffect ask)",
        iterations=300,
    ),
)


def run_benchmarks(
    *,
    cases: tuple[BenchmarkCase, ...] = DEFAULT_CASES,
    phases: tuple[BenchmarkPhase, ...] = ("source", "lower", "ir"),
    repeat: int = 3,
    warmup: int = 1,
) -> tuple[BenchmarkResult, ...]:
    results: list[BenchmarkResult] = []
    for case in cases:
        for phase in phases:
            measurements = [
                _measure_case(case, phase) for _ in range(max(0, warmup) + max(1, repeat))
            ]
            samples = measurements[max(0, warmup) :]
            best = min(samples)
            mean = statistics.fmean(samples)
            median = statistics.median(samples)
            results.append(
                BenchmarkResult(
                    case=case.name,
                    phase=phase,
                    iterations=case.iterations,
                    repeat=max(1, repeat),
                    best_seconds=best,
                    mean_seconds=mean,
                    median_seconds=median,
                    ops_per_second=case.iterations / best,
                    seconds_per_iteration=best / case.iterations,
                )
            )
    return tuple(results)


def _measure_case(case: BenchmarkCase, phase: BenchmarkPhase) -> float:
    qy = Qy()
    if case.setup_source.strip():
        qy.evaluate_program(case.setup_source)

    if phase == "source":
        return _elapsed(lambda: _run_source_iterations(qy, case))
    if phase == "lower":
        return _elapsed(lambda: _run_lower_iterations(qy.env, case))
    program = _compile_case(qy.env, case)
    return _elapsed(lambda: _run_ir_iterations(qy.env, program, case.iterations))


def _run_source_iterations(qy: Qy, case: BenchmarkCase) -> None:
    for _ in range(case.iterations):
        qy.evaluate_source(case.source)


def _run_lower_iterations(env: Environment, case: BenchmarkCase) -> None:
    forms = read(case.source)
    for _ in range(case.iterations):
        expansion = macroexpand(forms, env)
        lower(expansion.forms, env)


def _run_ir_iterations(env: Environment, program: ProgramIR, iterations: int) -> None:
    for _ in range(iterations):
        run_async(IRVirtualMachine(env).evaluate_program(program))


def _compile_case(env: Environment, case: BenchmarkCase) -> ProgramIR:
    expansion = macroexpand(read(case.source), env)
    return lower(expansion.forms, env)


def _elapsed(func: Callable[[], None]) -> float:
    start = time.perf_counter()
    func()
    return time.perf_counter() - start


def _selected_cases(names: set[str]) -> tuple[BenchmarkCase, ...]:
    if not names:
        return DEFAULT_CASES
    return tuple(case for case in DEFAULT_CASES if case.name in names)


def _format_results(results: tuple[BenchmarkResult, ...]) -> str:
    lines = [
        "case           phase    iter    best ms    mean ms    us/op      ops/s",
        "-------------  -------  ------  ---------  ---------  ---------  ---------",
    ]
    for result in results:
        lines.append(
            f"{result.case:<13}  "
            f"{result.phase:<7}  "
            f"{result.iterations:>6}  "
            f"{result.best_seconds * 1000:>9.3f}  "
            f"{result.mean_seconds * 1000:>9.3f}  "
            f"{result.seconds_per_iteration * 1_000_000:>9.3f}  "
            f"{result.ops_per_second:>9.1f}"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run Qy performance benchmarks.")
    parser.add_argument("--case", action="append", default=[], help="case name to run")
    parser.add_argument(
        "--phase",
        action="append",
        choices=("source", "lower", "ir"),
        default=[],
        help="benchmark phase to run",
    )
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    args = parser.parse_args(argv)

    cases = _selected_cases(set(args.case))
    phases = tuple(args.phase) if args.phase else ("source", "lower", "ir")
    results = run_benchmarks(
        cases=cases,
        phases=phases,
        repeat=args.repeat,
        warmup=args.warmup,
    )
    if args.json:
        print(json.dumps([asdict(result) for result in results], indent=2))
        return
    print(_format_results(results))


if __name__ == "__main__":
    main()
