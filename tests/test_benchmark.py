from qy.benchmark import BenchmarkCase
from qy.benchmark import run_benchmarks


def test_benchmark_runner_smoke_test():
    results = run_benchmarks(
        cases=(BenchmarkCase("tiny", "(+ 1 2)", iterations=1),),
        phases=("source", "lower", "ir"),
        repeat=1,
        warmup=0,
    )

    assert {result.phase for result in results} == {"source", "lower", "ir"}
    assert all(result.case == "tiny" for result in results)
    assert all(result.iterations == 1 for result in results)
    assert all(result.best_seconds > 0 for result in results)
    assert all(result.ops_per_second > 0 for result in results)
