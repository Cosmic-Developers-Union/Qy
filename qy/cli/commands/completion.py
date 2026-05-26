# -*- coding: utf-8 -*-

"""`qy completion` 命令入口。."""

from typing import Annotated
from typing import Any

import typer

from qy.cli._common import CLI_COMMANDS


def _completion_script(shell: str) -> str:
    shell = shell.lower()
    commands = " ".join(CLI_COMMANDS)
    if shell == "bash":
        return f"""# qy bash completion
_qy_complete() {{
  local cur
  COMPREPLY=()
  cur="${{COMP_WORDS[COMP_CWORD]}}"
  if [[ $COMP_CWORD -eq 1 ]]; then
    COMPREPLY=( $(compgen -W "{commands}" -- "$cur") $(compgen -f -- "$cur") )
  else
    COMPREPLY=( $(compgen -f -- "$cur") )
  fi
}}
complete -o default -o bashdefault -F _qy_complete qy
"""
    if shell == "zsh":
        command_specs = " ".join(f"'{command}:qy {command}'" for command in CLI_COMMANDS)
        return f"""#compdef qy
_qy() {{
  local -a commands
  commands=({command_specs})
  _arguments \\
    '1:command:->commands' \\
    '*:file:_files'
  case $state in
    commands)
      _describe 'command' commands
      _files
      ;;
  esac
}}
compdef _qy qy
"""
    if shell == "sh":
        return f"""# POSIX sh has no standard programmable completion API.
# Source this file to expose a portable helper with qy command names.
qy_completion_commands() {{
  printf '%s\\n' {commands}
}}
"""
    raise ValueError("unsupported shell; expected one of: bash, zsh, sh")


def register(app: Any) -> None:
    """将 completion 命令注册到给定的 typer 应用。."""

    @app.command("completion")
    def completion_command(
        shell: Annotated[
            str,
            typer.Argument(help="Shell name: bash, zsh, or sh."),
        ],
    ) -> None:
        """输出 shell completion 脚本."""
        try:
            typer.echo(_completion_script(shell), nl=False)
        except ValueError as e:
            typer.secho(str(e), fg=typer.colors.RED, err=True)
            raise typer.Exit(2) from e
