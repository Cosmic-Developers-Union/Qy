# coding: utf-8
# ruff: noqa: I001

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from qy.reader import Symbol
from qy.runtime import Qy


qy = Qy()

qy.env.define(Symbol("host-answer"), 41)


@qy.register_pure("host-inc")
def host_inc(value: int) -> int:
    return value + 1


result = qy.evaluate_source("(host-inc host-answer)")
print(result)
