from qy.benchmark import BenchmarkCase
from qy.benchmark import BenchmarkResult
from qy.benchmark import compare_benchmarks
from qy.benchmark import load_benchmark_baseline
from qy.benchmark import run_benchmarks
from qy.benchmark import write_benchmark_baseline


def test_benchmark_runner_smoke_test():
    results = run_benchmarks(
        cases=(BenchmarkCase("tiny", "(+ 1 2)", iterations=1),),
        phases=(
            "source",
            "macroexpand",
            "hir_lower",
            "mir_lower",
            "lir_lower",
            "bytecode_compile",
            "bytecode_vm",
        ),
        repeat=1,
        warmup=0,
    )

    assert {result.phase for result in results} == {
        "source",
        "macroexpand",
        "hir_lower",
        "mir_lower",
        "lir_lower",
        "bytecode_compile",
        "bytecode_vm",
    }
    assert all(result.case == "tiny" for result in results)
    assert all(result.iterations == 1 for result in results)
    assert all(result.best_seconds > 0 for result in results)
    assert all(result.ops_per_second > 0 for result in results)


def test_benchmark_runner_runs_effect_benchmark_in_bytecode_phase():
    results = run_benchmarks(
        cases=(
            BenchmarkCase(
                "effect",
                "(handle (+ 1 (perform ask 41)) ((ask (arg k) (resume k arg))))",
                setup_source="(defeffect ask)",
                iterations=1,
            ),
        ),
        phases=("bytecode_vm",),
        repeat=1,
        warmup=0,
    )

    assert len(results) == 1
    assert results[0].case == "effect"
    assert results[0].phase == "bytecode_vm"


def test_benchmark_compare_reports_only_threshold_regressions():
    baseline = (
        BenchmarkResult("tiny", "lir_lower", 10, 1, 1.0, 1.0, 1.0, 10.0, 0.1),
        BenchmarkResult("tiny", "hir_lower", 10, 1, 2.0, 2.0, 2.0, 5.0, 0.2),
    )
    current = (
        BenchmarkResult("tiny", "lir_lower", 10, 1, 1.2, 1.2, 1.2, 8.0, 0.12),
        BenchmarkResult("tiny", "hir_lower", 10, 1, 2.1, 2.1, 2.1, 4.8, 0.21),
    )

    regressions = compare_benchmarks(current, baseline, max_regression_percent=10)

    assert len(regressions) == 1
    assert regressions[0].case == "tiny"
    assert regressions[0].phase == "lir_lower"


def test_benchmark_baseline_roundtrip(tmp_path):
    path = tmp_path / "baseline.json"
    results = (BenchmarkResult("tiny", "source", 1, 1, 0.1, 0.1, 0.1, 10.0, 0.1),)

    write_benchmark_baseline(results, path)

    assert load_benchmark_baseline(path) == results
