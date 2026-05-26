# coding: utf-8

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from qy.benchmark.types import BenchmarkRegression
from qy.benchmark.types import BenchmarkResult

__all__ = [
    "compare_benchmarks",
    "load_benchmark_baseline",
    "write_benchmark_baseline",
]


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
