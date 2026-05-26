# coding: utf-8

from __future__ import annotations

import asyncio
import statistics
import time
from collections.abc import Callable

from qy.async_utils import run_coro
from qy.backend.vm.bytecode import BytecodeProgram
from qy.benchmark.types import BenchmarkCase
from qy.benchmark.types import BenchmarkPhase
from qy.benchmark.types import BenchmarkResult
from qy.frontend.reader import read
from qy.passes.build import bytecode_artifact
from qy.passes.build import compile_source_to_kind_async
from qy.passes.pass_base import PipelineSession
from qy.runtime import Qy
from qy.session.runtime_space import RuntimeSpace as Environment
from qy.vm.instance.machine import RegisterVirtualMachine

__all__ = ["run_benchmarks"]


def run_benchmarks(
    *,
    cases: tuple[BenchmarkCase, ...] | None = None,
    phases: tuple[BenchmarkPhase, ...] = (
        "source",
        "macroexpand",
        "hir_lower",
        "mir_lower",
        "lir_lower",
        "bytecode_compile",
        "bytecode_vm",
    ),
    repeat: int = 3,
    warmup: int = 1,
) -> tuple[BenchmarkResult, ...]:
    from qy.benchmark import DEFAULT_CASES

    if cases is None:
        cases = DEFAULT_CASES
    results: list[BenchmarkResult] = []
    for case in cases:
        for phase in phases:
            measurements: list[float] = []
            for _ in range(max(0, warmup) + max(1, repeat)):
                measurement = _measure_case(case, phase)
                if measurement is None:
                    measurements = []
                    break
                measurements.append(measurement)
            if not measurements:
                continue
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


def _measure_case(case: BenchmarkCase, phase: BenchmarkPhase) -> float | None:
    qy = Qy()
    if case.setup_source.strip():
        qy.evaluate_program(case.setup_source)

    read(case.source)

    if phase == "source":
        return _elapsed(lambda: _run_source_iterations(qy, case))
    if phase == "macroexpand":
        return _elapsed(lambda: _run_pipeline_iterations(qy.env, case, kind="core-ast"))
    if phase == "hir_lower":
        return _elapsed(lambda: _run_pipeline_iterations(qy.env, case, kind="hir"))
    if phase == "mir_lower":
        return _elapsed(lambda: _run_pipeline_iterations(qy.env, case, kind="mir"))
    if phase == "lir_lower":
        return _elapsed(lambda: _run_pipeline_iterations(qy.env, case, kind="lir"))
    if phase == "bytecode_compile":
        return _elapsed(lambda: _run_pipeline_iterations(qy.env, case, kind="bytecode"))

    bytecode = _compile_bytecode(qy.env, case.source)
    if bytecode is None or not bytecode.ok:
        return None
    return _elapsed(lambda: _run_bytecode_iterations(qy.env, bytecode, case.iterations))


def _compile_bytecode(env: Environment, source: str) -> BytecodeProgram | None:
    session = PipelineSession(env=env)
    result = run_coro(compile_source_to_kind_async(source, session, kind="bytecode"))
    try:
        return bytecode_artifact(result)
    except TypeError:
        return None


def _run_source_iterations(qy: Qy, case: BenchmarkCase) -> None:
    for _ in range(case.iterations):
        qy.evaluate_source(case.source)


def _run_pipeline_iterations(env: Environment, case: BenchmarkCase, *, kind: str) -> None:
    for _ in range(case.iterations):
        session = PipelineSession(env=env)
        run_coro(compile_source_to_kind_async(case.source, session, kind=kind))


def _run_bytecode_iterations(env: Environment, program: BytecodeProgram, iterations: int) -> None:
    for _ in range(iterations):
        asyncio.run(RegisterVirtualMachine(program, env).evaluate_program())


def _elapsed(func: Callable[[], None]) -> float:
    start = time.perf_counter()
    func()
    return time.perf_counter() - start
