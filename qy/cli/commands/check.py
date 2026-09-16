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

import click

from qy.cli._common import diagnostic_color
from qy.cli._common import format_diagnostic
from qy.cli._common import read_debug_source
from qy.cli._common import secho
from qy.tools.check import analyze_source


def register(group: click.Group) -> None:
    """将 check / typecheck 命令注册到给定的 click group。."""

    def _check_path(path: str) -> None:
        source, source_name = read_debug_source(path)
        analysis = analyze_source(source)
        for diagnostic in analysis.diagnostics:
            secho(
                format_diagnostic(source_name, diagnostic),
                fg=diagnostic_color(diagnostic),
                err=True,
            )
        if not analysis.ok:
            raise click.exceptions.Exit(1)
        secho(f"{source_name}: ok", fg="green")

    @group.command("check")
    @click.argument("path", type=str)
    def check_command(path: str) -> None:
        """Run static analysis on a Qy source file. Use '-' for stdin."""
        _check_path(path)

    @group.command("typecheck")
    @click.argument("path", type=str)
    def typecheck_command(path: str) -> None:
        """Run static analysis (alias of check). Use '-' for stdin."""
        _check_path(path)
