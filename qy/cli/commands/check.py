# -*- coding: utf-8 -*-
# Copyright (C) 2025 Cosmic-Developers-Union (CDU), All rights reserved.

"""`qy check` / `qy typecheck` 命令入口。.

目标：
- 承载静态检查命令入口。
- 调用 `qy.tools.check` 提供的 public API。

禁止：
- 不得在 CLI 命令里定义 analyzer 语义。
"""

from __future__ import annotations

from pathlib import Path

import click

from qy.cli._common import diagnostic_color
from qy.cli._common import format_diagnostic
from qy.cli._common import secho
from qy.tools.check import analyze_source


def register(group: click.Group) -> None:
    """将 check / typecheck 命令注册到给定的 click group。."""

    def _check_path(path: Path) -> None:
        analysis = analyze_source(path.read_text(encoding="utf-8"))
        for diagnostic in analysis.diagnostics:
            secho(
                format_diagnostic(path, diagnostic),
                fg=diagnostic_color(diagnostic),
                err=True,
            )
        if not analysis.ok:
            raise click.exceptions.Exit(1)
        secho(f"{path}: ok", fg="green")

    @group.command("check")
    @click.argument("path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
    def check_command(path: Path) -> None:
        """Run static analysis on a Qy source file."""
        _check_path(path)

    @group.command("typecheck")
    @click.argument("path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
    def typecheck_command(path: Path) -> None:
        """Alias for check."""
        _check_path(path)
