# coding: utf-8

"""性能基准测试工具."""

from __future__ import annotations

from qy.benchmark.compare import compare_benchmarks
from qy.benchmark.compare import load_benchmark_baseline
from qy.benchmark.compare import write_benchmark_baseline
from qy.benchmark.runner import run_benchmarks
from qy.benchmark.types import BenchmarkCase
from qy.benchmark.types import BenchmarkPhase
from qy.benchmark.types import BenchmarkRegression
from qy.benchmark.types import BenchmarkResult

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
    BenchmarkCase(
        "module-import",
        "(add 1 2)",
        setup_source="(from qy.num import + as add)",
        iterations=500,
    ),
    BenchmarkCase(
        "effect-heavy",
        "(handle (perform ask 1) ((ask (x k) (resume k x))))",
        setup_source="(defeffect ask)",
        iterations=200,
    ),
    BenchmarkCase(
        "macro-heavy",
        "(my-if true 1 2)",
        setup_source="(macro my-if (c t e) (quasiquote (cond ((unquote c) (unquote t)) (true (unquote e)))))",
        iterations=500,
    ),
)
