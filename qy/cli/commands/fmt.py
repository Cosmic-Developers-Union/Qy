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

import click

from qy.cli._common import secho
from qy.frontend.reader import ReaderSyntaxError
from qy.tools.fmt import format_source


def register(group: click.Group) -> None:
    """将 fmt 命令注册到给定的 click group。."""

    @group.command("fmt")
    @click.argument("path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
    @click.option(
        "--write",
        "-w",
        is_flag=True,
        help="Rewrite the file in place.",
    )
    def format_command(path: Path, write: bool) -> None:
        """Format Qy source code with syntax checking."""
        try:
            source = path.read_text(encoding="utf-8")
            formatted = format_source(source)
            if write:
                path.write_text(formatted, encoding="utf-8")
                secho(f"formatted {path}", fg="green")
                return
            click.echo(formatted, nl=False)
        except ReaderSyntaxError as e:
            secho(f"{path}: syntax error: {e}", fg="red", err=True)
            raise click.exceptions.Exit(1) from e
        except OSError as e:
            secho(f"{path}: {e}", fg="red", err=True)
            raise click.exceptions.Exit(1) from e
