# coding: utf-8

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from qy.benchmark.compare import compare_benchmarks
from qy.benchmark.compare import load_benchmark_baseline
from qy.benchmark.compare import write_benchmark_baseline
from qy.benchmark.runner import run_benchmarks
from qy.benchmark.types import BenchmarkRegression
from qy.benchmark.types import BenchmarkResult

__all__: list[str] = []

BenchmarkPhaseChoices = (
    "source",
    "macroexpand",
    "hir_lower",
    "mir_lower",
    "lir_lower",
    "bytecode_compile",
    "bytecode_vm",
)


def main(argv: list[str] | None = None) -> None:
    from qy.benchmark import DEFAULT_CASES

    parser = argparse.ArgumentParser(description="Run Qy performance benchmarks.")
    parser.add_argument("--case", action="append", default=[], help="case name to run")
    parser.add_argument(
        "--phase",
        action="append",
        choices=BenchmarkPhaseChoices,
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

    cases = _selected_cases(DEFAULT_CASES, set(args.case))
    phases = tuple(args.phase) if args.phase else BenchmarkPhaseChoices
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


def _selected_cases(default_cases: tuple, names: set[str]) -> tuple:
    if not names:
        return default_cases
    return tuple(case for case in default_cases if case.name in names)


def _format_results(results: tuple[BenchmarkResult, ...]) -> str:
    lines = [
        "case           phase             iter    best ms    mean ms    us/op      ops/s",
        "-------------  ----------------  ------  ---------  ---------  ---------  ---------",
    ]
    for result in results:
        lines.append(
            f"{result.case:<13}  "
            f"{result.phase:<16}  "
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
        "case           phase             baseline us/op  current us/op  regression",
        "-------------  ----------------  --------------  -------------  ----------",
    ]
    for regression in regressions:
        lines.append(
            f"{regression.case:<13}  "
            f"{regression.phase:<16}  "
            f"{regression.baseline_seconds_per_iteration * 1_000_000:>14.3f}  "
            f"{regression.current_seconds_per_iteration * 1_000_000:>13.3f}  "
            f"{regression.regression_percent:>9.2f}%"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    main()
