# -*- coding: utf-8 -*-
# Copyright (C) 2025 Cosmic-Developers-Union (CDU), All rights reserved.

"""`qy fmt` 命令入口。.

目标：
- 承载格式化命令入口。
- 调用 `qy.tools.fmt` 提供的 public API。

禁止：
- 不得在 CLI 命令里定义 formatter 语义。
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated
from typing import Any

import typer

from qy.frontend.reader import ReaderSyntaxError
from qy.tools.fmt import format_source


def register(app: Any) -> None:
    """将 fmt 命令注册到给定的 typer 应用。."""

    @app.command("fmt")
    def format_command(
        path: Annotated[Path, typer.Argument(help="Qy source file to format.")],
        write: Annotated[
            bool,
            typer.Option("--write", "-w", help="Rewrite the file in place."),
        ] = False,
    ) -> None:
        """Format Qy source code with syntax checking."""
        try:
            source = path.read_text(encoding="utf-8")
            formatted = format_source(source)
            if write:
                path.write_text(formatted, encoding="utf-8")
                typer.secho(f"formatted {path}", fg=typer.colors.GREEN)
                return
            typer.echo(formatted, nl=False)
        except ReaderSyntaxError as e:
            typer.secho(f"{path}: syntax error: {e}", fg=typer.colors.RED, err=True)
            raise typer.Exit(1) from e
        except OSError as e:
            typer.secho(f"{path}: {e}", fg=typer.colors.RED, err=True)
            raise typer.Exit(1) from e
