#!/usr/bin/env python3
"""Python host wrapper for the Qy meta-interpreter.

The meta-interpreter is now self-sufficient: ``meta-interp/main.qy`` reads its
input path from CLI args and uses the host ``read-file`` capability itself.
This wrapper simply forwards to:

    qy run meta-interp/main.qy -- <source.qy>

Usage:
    python meta-interp/run_host.py <source.qy>
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: run_host.py <file.qy>", file=sys.stderr)
        return 2
    src_path = Path(sys.argv[1])
    if not src_path.exists():
        print(f"file not found: {src_path}", file=sys.stderr)
        return 2
    meta_main = Path(__file__).resolve().parent / "main.qy"
    result = subprocess.run(
        ["uv", "run", "qy", "run", str(meta_main), "--", str(src_path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
