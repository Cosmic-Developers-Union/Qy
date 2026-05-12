# coding: utf-8

from __future__ import annotations

import argparse
import json
import statistics
import time
from collections.abc import Callable
from dataclasses import asdict
from dataclasses import dataclass
from pathlib import Path
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
    "BenchmarkRegression",
    "BenchmarkResult",
    "compare_benchmarks",
    "load_benchmark_baseline",
    "run_benchmarks",
    "write_benchmark_baseline",
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


@dataclass(frozen=True, slots=True)
class BenchmarkRegression:
    case: str
    phase: BenchmarkPhase
    baseline_seconds_per_iteration: float
    current_seconds_per_iteration: float
    regression_percent: float


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


def compare_benchmarks(
    current: tuple[BenchmarkResult, ...],
    baseline: tuple[BenchmarkResult, ...],
    *,
    max_regression_percent: float = 10.0,
) -> tuple[BenchmarkRegression, ...]:
    baseline_by_key = {
        (result.case, result.phase): result
        for result in baseline
        if result.seconds_per_iteration > 0
    }
    regressions: list[BenchmarkRegression] = []
    for result in current:
        baseline_result = baseline_by_key.get((result.case, result.phase))
        if baseline_result is None:
            continue
        regression_percent = (
            (result.seconds_per_iteration / baseline_result.seconds_per_iteration) - 1.0
        ) * 100.0
        if regression_percent > max_regression_percent:
            regressions.append(
                BenchmarkRegression(
                    case=result.case,
                    phase=result.phase,
                    baseline_seconds_per_iteration=baseline_result.seconds_per_iteration,
                    current_seconds_per_iteration=result.seconds_per_iteration,
                    regression_percent=regression_percent,
                )
            )
    return tuple(regressions)


def load_benchmark_baseline(path: str | Path) -> tuple[BenchmarkResult, ...]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        raw = raw.get("results", [])
    if not isinstance(raw, list):
        raise ValueError("benchmark baseline must be a JSON list or an object with results")
    return tuple(BenchmarkResult(**item) for item in raw)


def write_benchmark_baseline(results: tuple[BenchmarkResult, ...], path: str | Path) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps([asdict(result) for result in results], indent=2) + "\n",
        encoding="utf-8",
    )


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


def _format_regressions(regressions: tuple[BenchmarkRegression, ...]) -> str:
    lines = [
        "benchmark regressions:",
        "case           phase    baseline us/op  current us/op  regression",
        "-------------  -------  --------------  -------------  ----------",
    ]
    for regression in regressions:
        lines.append(
            f"{regression.case:<13}  "
            f"{regression.phase:<7}  "
            f"{regression.baseline_seconds_per_iteration * 1_000_000:>14.3f}  "
            f"{regression.current_seconds_per_iteration * 1_000_000:>13.3f}  "
            f"{regression.regression_percent:>9.2f}%"
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
    parser.add_argument("--baseline", type=Path, help="compare against a benchmark JSON file")
    parser.add_argument("--write-baseline", type=Path, help="write current results as JSON")
    parser.add_argument("--max-regression-percent", type=float, default=10.0)
    args = parser.parse_args(argv)

    cases = _selected_cases(set(args.case))
    phases = tuple(args.phase) if args.phase else ("source", "lower", "ir")
    results = run_benchmarks(
        cases=cases,
        phases=phases,
        repeat=args.repeat,
        warmup=args.warmup,
    )
    regressions: tuple[BenchmarkRegression, ...] = ()
    if args.baseline is not None:
        regressions = compare_benchmarks(
            results,
            load_benchmark_baseline(args.baseline),
            max_regression_percent=args.max_regression_percent,
        )
    if args.write_baseline is not None:
        write_benchmark_baseline(results, args.write_baseline)
    if args.json:
        payload: object
        if args.baseline is None:
            payload = [asdict(result) for result in results]
        else:
            payload = {
                "results": [asdict(result) for result in results],
                "regressions": [asdict(regression) for regression in regressions],
            }
        print(json.dumps(payload, indent=2))
        if regressions:
            raise SystemExit(1)
        return
    print(_format_results(results))
    if regressions:
        print()
        print(_format_regressions(regressions))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
