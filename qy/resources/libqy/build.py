# coding: utf-8
"""Build libqy.a from qy.h and runtime.c.

Usage:
    python build.py          # build in default location
    python build.py --clean  # clean build artifacts

Output:
    include/qy.h    — header (already present, copy if needed)
    libqy.a        — static library (archive)
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()
INCLUDE_DIR = SCRIPT_DIR / "include"
SRC_DIR = SCRIPT_DIR / "src"
LIB_DIR = SCRIPT_DIR
HEADER = INCLUDE_DIR / "qy.h"
SOURCE = SRC_DIR / "runtime.c"
ARCHIVE = LIB_DIR / "libqy.a"
ARCHIVER = os.environ.get("AR", "ar")
CC = os.environ.get("CC", "gcc")


def build_libqy(clean: bool = False) -> None:
    """Compile runtime.c and archive into libqy.a."""
    if clean:
        if ARCHIVE.exists():
            ARCHIVE.unlink()
        obj = SRC_DIR / "runtime.o"
        if obj.exists():
            obj.unlink()
        print("cleaned libqy.a and runtime.o")
        return

    if not HEADER.exists():
        print(f"error: header not found: {HEADER}", file=sys.stderr)
        sys.exit(1)
    if not SOURCE.exists():
        print(f"error: source not found: {SOURCE}", file=sys.stderr)
        sys.exit(1)

    obj = SRC_DIR / "runtime.o"
    print(f"compiling {SOURCE} ...")
    r = subprocess.run(
        [
            CC,
            "-Wall",
            "-Wextra",
            "-pedantic",
            "-std=c11",
            "-I",
            str(INCLUDE_DIR),
            "-c",
            str(SOURCE),
            "-o",
            str(obj),
        ],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        print(f"compile failed:\n{r.stderr}", file=sys.stderr)
        sys.exit(1)

    print(f"archiving {ARCHIVE} ...")
    if ARCHIVE.exists():
        ARCHIVE.unlink()
    r = subprocess.run(
        [ARCHIVER, "rcs", str(ARCHIVE), str(obj)],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        print(f"ar failed:\n{r.stderr}", file=sys.stderr)
        sys.exit(1)

    print(f"libqy.a built: {ARCHIVE}")
    # Verify symbols
    r = subprocess.run(
        ["nm", str(ARCHIVE)],
        capture_output=True,
        text=True,
    )
    for line in r.stdout.splitlines():
        if " T " in line or " t " in line:
            print(f"  {line.strip()}")


if __name__ == "__main__":
    clean = "--clean" in sys.argv
    build_libqy(clean=clean)
