# coding: utf-8
"""Link LLVM IR to a native executable.

Pipeline:
    .ll text -> llc -> .o -> gcc link -> a.out

The linker:
    1. Writes LLVM IR to a temp file
    2. Invokes llc to compile to object file
    3. Invokes gcc to link with libqy
    4. Returns the output executable path

生成的 LLVM 模块已提供 qy_fn_table / qy_fn_table_size / qy_main / main
    （见 qy/backend/llvm/emit.py），因此只与 libqy.a 链接，不再生成 C wrapper。

Environment variables:
    QY_LLC       — path to llc (default: "llc")
    QY_CC        — path to C compiler (default: "gcc")
    QY_LLVM_DIR  — directory containing LLVM tools (default: search PATH)
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

__all__ = ["CompileResult", "link"]


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


class CompileResult:
    """Result of compiling a Qy program to an executable."""

    def __init__(
        self,
        executable: Path,
        ll_text: str,
        ll_path: Path,
        obj_path: Path,
    ):
        self.executable = executable
        self.ll_text = ll_text
        self.ll_path = ll_path
        self.obj_path = obj_path

    def run(self, *args: str) -> subprocess.CompletedProcess:
        """Run the executable with the given arguments."""
        return subprocess.run(
            [str(self.executable), *list(args)],
            capture_output=True,
            text=True,
        )


# ---------------------------------------------------------------------------
# Default tool paths
# ---------------------------------------------------------------------------


def _llc() -> str:
    return os.environ.get("QY_LLC", "llc")


def _cc() -> str:
    return os.environ.get("QY_CC", "gcc")


# ---------------------------------------------------------------------------
# Main linking function
# ---------------------------------------------------------------------------


def link(
    ll_text: str,
    output_dir: Path | str | None = None,
    output_name: str = "a.out",
    libqy_dir: Path | str | None = None,
    extra_cflags: list[str] | None = None,
) -> CompileResult:
    """Compile LLVM IR text to a native executable.

    Args:
        ll_text: LLVM IR source text
        output_dir: directory for output files (default: system temp dir)
        output_name: name of the output executable
        libqy_dir: directory containing libqy.a and qy.h (default: qy/resources/libqy)
        extra_cflags: additional flags to pass to gcc

    Returns:
        CompileResult with paths to all artifacts
    """
    if output_dir is None:
        output_dir = Path(tempfile.gettempdir()) / "qy_llvm"
    else:
        output_dir = Path(output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)

    ll_path = output_dir / f"{output_name}.ll"
    obj_path = output_dir / f"{output_name}.o"
    exe_path = output_dir / output_name

    # Default libqy dir
    if libqy_dir is None:
        libqy_dir = Path(__file__).parent.parent.parent / "resources" / "libqy"
    libqy_dir = Path(libqy_dir)

    # Write LLVM IR
    ll_path.write_text(ll_text)

    # Step 1: llc -relocation-model=pic -filetype=obj hello.ll -o hello.o
    # PIC 是默认 PIE 链接的前提：否则对只读数据段的引用会生成 32-bit 绝对重定位。
    llc_result = subprocess.run(
        [_llc(), "-relocation-model=pic", "-filetype=obj", str(ll_path), "-o", str(obj_path)],
        capture_output=True,
        text=True,
    )
    if llc_result.returncode != 0:
        raise CompilationError(f"llc failed:\n{llc_result.stderr}")

    # Find libqy.a
    libqy_a = libqy_dir / "libqy.a"
    if not libqy_a.exists():
        raise CompilationError(f"libqy.a not found at {libqy_a}. Run: make libqy")

    # 生成的 LLVM 模块已提供 qy_fn_table / qy_fn_table_size / qy_main / main，
    # 因此只链接 libqy.a，不再生成会重复定义这些符号的 C wrapper。
    link_cmd = [
        _cc(),
        "-no-pie",
        str(obj_path),
        str(libqy_a),
        "-o",
        str(exe_path),
    ]
    if extra_cflags:
        link_cmd.extend(extra_cflags)

    link_result = subprocess.run(link_cmd, capture_output=True, text=True)
    if link_result.returncode != 0:
        raise CompilationError(f"link failed:\n{link_result.stderr}")

    return CompileResult(
        executable=exe_path,
        ll_text=ll_text,
        ll_path=ll_path,
        obj_path=obj_path,
    )


class CompilationError(Exception):
    """Raised when compilation or linking fails."""

    pass
