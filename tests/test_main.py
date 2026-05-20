# coding: utf-8
"""测试 qy.__main__ 入口点。."""

from __future__ import annotations

import subprocess
import sys


def test_main_entry_point_runs():
    """测试 python -m qy 可以运行。."""
    result = subprocess.run(
        [sys.executable, "-m", "qy", "--help"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0
    assert "Usage:" in result.stdout or "usage:" in result.stdout.lower()


def test_main_entry_point_invalid_command():
    """测试 python -m qy 对无效命令返回错误。."""
    result = subprocess.run(
        [sys.executable, "-m", "qy", "invalid-command-xyz"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    # Should fail with non-zero exit code
    assert result.returncode != 0
