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
from typing import Annotated
from typing import Any

import typer

from qy.tools.check import analyze_source


def register(app: Any) -> None:
    """将 check / typecheck 命令注册到给定的 typer 应用。."""
    from qy.cli._common import diagnostic_color
    from qy.cli._common import format_diagnostic

    def _check_path(path: Path) -> None:
        analysis = analyze_source(path.read_text(encoding="utf-8"))
        for diagnostic in analysis.diagnostics:
            typer.secho(
                format_diagnostic(path, diagnostic),
                fg=diagnostic_color(diagnostic),
                err=True,
            )
        if not analysis.ok:
            raise typer.Exit(1)
        typer.secho(f"{path}: ok", fg=typer.colors.GREEN)

    @app.command("check")
    def check_command(
        path: Annotated[Path, typer.Argument(help="Qy source file to check.")],
    ) -> None:
        _check_path(path)

    @app.command("typecheck")
    def typecheck_command(
        path: Annotated[Path, typer.Argument(help="Alias for check.")],
    ) -> None:
        _check_path(path)
