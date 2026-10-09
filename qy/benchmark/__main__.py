# coding: utf-8
"""``python -m qy.benchmark`` 入口。.

目标：
- 让 Makefile 的 ``bench`` / ``bench-baseline`` / ``bench-check`` 目标（以及
  ``python -m qy.benchmark``）可用，与 ``qy-bench`` console script 等价。
"""

from __future__ import annotations

from qy.benchmark.cli import main

if __name__ == "__main__":
    main()
