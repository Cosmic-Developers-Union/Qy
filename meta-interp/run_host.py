#!/usr/bin/env python3
"""Python host for the Qy meta-interpreter.

Reads a Qy source file, encodes it as a Qy string literal, and invokes
the Qy meta-interpreter to evaluate it.

Usage:
    python meta-interp/run_host.py <source.qy>
"""
from __future__ import annotations

import sys
import json
import subprocess
from pathlib import Path


def encode_qy_string(s: str) -> str:
    """Encode a Python string as a Qy string literal.

    Qy strings use double-quotes with backslash escapes. For simplicity,
    we use Python's repr-like escaping wrapped in double quotes.
    """
    # Use JSON-style escaping but produce a valid Qy string literal.
    out = ['"']
    for ch in s:
        code = ord(ch)
        if ch == '"':
            out.append('\\"')
        elif ch == '\\':
            out.append('\\\\')
        elif ch == '\n':
            out.append('\\n')
        elif ch == '\r':
            out.append('\\r')
        elif ch == '\t':
            out.append('\\t')
        elif code < 0x20 or code == 0x7f:
            out.append(f'\\x{code:02x}')
        elif code > 0x7f:
            out.append(f'\\u{{{code:x}}}')
        else:
            out.append(ch)
    out.append('"')
    return ''.join(out)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: run_host.py <file.qy>", file=sys.stderr)
        return 2
    src_path = Path(sys.argv[1])
    if not src_path.exists():
        print(f"file not found: {src_path}", file=sys.stderr)
        return 2
    source = src_path.read_text(encoding="utf-8")

    # Read main.qy as the prelude; embed source as Qy string and call meta-run.
    main_path = Path("meta-interp/main.qy")
    main_src = main_path.read_text(encoding="utf-8")
    encoded = encode_qy_string(source)
    driver = main_src + "\n" + f'(meta-run {encoded})\n'
    driver_path = Path("meta-interp/_driver.qy")
    driver_path.write_text(driver, encoding="utf-8")
    try:
        result = subprocess.run(
            ["uv", "run", "qy", "run", str(driver_path)],
            capture_output=True, text=True, encoding="utf-8",
        )
        sys.stdout.write(result.stdout)
        sys.stderr.write(result.stderr)
        sys.stderr.write(f"\n[debug] rc={result.returncode}\n")
        return result.returncode
    finally:
        sys.stderr.write(f"[debug] driver={driver_path}\n")
        # keep for debugging


if __name__ == "__main__":
    sys.exit(main())
