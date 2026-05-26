# coding: utf-8

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

BenchmarkPhase = Literal[
    "source",
    "macroexpand",
    "hir_lower",
    "mir_lower",
    "lir_lower",
    "bytecode_compile",
    "bytecode_vm",
]


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
