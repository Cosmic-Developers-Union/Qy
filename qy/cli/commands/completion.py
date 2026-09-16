# -*- coding: utf-8 -*-

"""`qy completion` 命令入口。."""

from __future__ import annotations

import click

from qy.cli._common import secho


def _command_names(group: click.Group) -> tuple[str, ...]:
    """从真实注册的 click group 派生命令清单，避免第二份命令事实。."""
    return tuple(sorted(group.commands))


def _completion_script(shell: str, command_names: tuple[str, ...]) -> str:
    shell = shell.lower()
    commands = " ".join(command_names)
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
        command_specs = " ".join(f"'{command}:qy {command}'" for command in command_names)
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


def register(group: click.Group) -> None:
    """将 completion 命令注册到给定的 click group。."""

    @group.command("completion")
    @click.argument("shell")
    def completion_command(shell: str) -> None:
        """Output shell completion script (bash, zsh, or sh)."""
        try:
            click.echo(_completion_script(shell, _command_names(group)), nl=False)
        except ValueError as e:
            secho(str(e), fg="red", err=True)
            raise click.exceptions.Exit(2) from e
