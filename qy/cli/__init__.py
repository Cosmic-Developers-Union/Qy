# coding: utf-8

import atexit
import sys
from pathlib import Path
from typing import Annotated
from typing import Any

from qy.analysis import Diagnostic
from qy.analysis import analyze_source
from qy.backend.vm.bytecode import dump_bytecode
from qy.backend.vm.bytecode import serialize_bytecode_json
from qy.display import format_value
from qy.errors import QyError
from qy.errors import format_qy_error
from qy.frontend.reader import ReaderSyntaxError
from qy.frontend.reader import read
from qy.frontend.reader import read_raw
from qy.ir import dump_ir
from qy.ir.lir import dump_lir
from qy.ir.mir import dump_mir
from qy.passes.lower_lir import lower_lir
from qy.runtime import Qy
from qy.std.profile import format_operator_docs
from qy.tools.fmt import dump_program
from qy.tools.fmt import format_source

INSTALL_CLI_MESSAGE = (
    "Qy CLI requires the optional cli dependency. Install with: pip install 'QyLang[cli]'"
)
INSTALL_LSP_MESSAGE = (
    "Qy LSP requires the optional lsp dependency. Install with: pip install 'QyLang[lsp]'"
)
CLI_COMMANDS = (
    "run",
    "repl",
    "expand",
    "hir",
    "mir",
    "lir",
    "bytecode",
    "export",
    "llvm",
    "fmt",
    "ast",
    "check",
    "typecheck",
    "operators",
    "lsp",
    "completion",
)
REPL_COMMANDS = (".help", ".env", ".ast", ".fmt", ".check", ".exit", ".quit")


def main() -> int:
    try:
        app = create_app()
    except ModuleNotFoundError as e:
        if e.name == "typer":
            print(INSTALL_CLI_MESSAGE, file=sys.stderr)
            return 2
        raise
    app()
    return 0


def create_app() -> Any:
    import click
    import typer
    from typer.core import TyperGroup

    class QyGroup(TyperGroup):
        def resolve_command(
            self, ctx: click.Context, args: list[str]
        ) -> tuple[str | None, click.Command | None, list[str]]:
            try:
                return super().resolve_command(ctx, args)
            except click.UsageError:
                if args and not args[0].startswith("-") and Path(args[0]).is_file():
                    command = self.get_command(ctx, "run")
                    return "run", command, args
                raise

    app = typer.Typer(
        add_completion=False,
        cls=QyGroup,
        epilog="Shortcut: qy FILE evaluates FILE.",
        help="Qy command line tools.",
        invoke_without_command=True,
        no_args_is_help=False,
    )

    @app.callback()
    def root(ctx: typer.Context) -> None:
        if ctx.invoked_subcommand is not None:
            return
        raise typer.Exit(repl(Qy()))

    @app.command("run")
    def run_command(
        path: Annotated[Path, typer.Argument(help="Qy source file to evaluate.")],
        args: Annotated[
            list[str] | None,
            typer.Argument(help="Arguments passed through to the Qy runtime program."),
        ] = None,
    ) -> None:
        try:
            qy = Qy()
            if args:
                from qy.std.testhost import set_cli_args

                set_cli_args(qy.env, tuple(args))
            typer.echo(format_value(qy.evaluate_file(path)))
        except QyError as e:
            typer.secho(format_qy_error(e), fg=typer.colors.RED, err=True)
            raise typer.Exit(1) from e

    @app.command("repl")
    def repl_command() -> None:
        raise typer.Exit(repl(Qy()))

    @app.command("expand")
    def expand_command(
        target: Annotated[
            str,
            typer.Argument(help="Qy source file to expand, or - to read from stdin."),
        ],
    ) -> None:
        qy = Qy()
        source, source_name = _read_debug_source(target)
        expansion = qy.macroexpand_source(source, source_name=source_name)
        if expansion.forms:
            typer.echo(dump_program(expansion.forms), nl=False)
        if _print_debug_diagnostics(source_name, expansion.diagnostics):
            raise typer.Exit(1)

    @app.command("hir")
    def hir_command(
        target: Annotated[
            str,
            typer.Argument(help="Qy source file to lower, or - to read from stdin."),
        ],
    ) -> None:
        qy = Qy()
        source, source_name = _read_debug_source(target)
        expansion = qy.macroexpand_source(source, source_name=source_name)
        has_errors = _print_debug_diagnostics(source_name, expansion.diagnostics)
        if expansion.forms:
            program = qy.lower(expansion.forms)
            typer.echo(dump_ir(program), nl=False)
            has_errors = _print_debug_diagnostics(source_name, program.diagnostics) or has_errors
        if has_errors:
            raise typer.Exit(1)

    @app.command("mir")
    def mir_command(
        target: Annotated[
            str,
            typer.Argument(help="Qy source file to lower into MIR, or - to read from stdin."),
        ],
    ) -> None:
        qy = Qy()
        source, source_name = _read_debug_source(target)
        expansion = qy.macroexpand_source(source, source_name=source_name)
        has_errors = _print_debug_diagnostics(source_name, expansion.diagnostics)
        if expansion.forms:
            program = qy.lower(expansion.forms)
            has_errors = _print_debug_diagnostics(source_name, program.diagnostics) or has_errors
            mir = qy.lower_mir(program)
            typer.echo(dump_mir(mir), nl=False)
            has_errors = _print_debug_diagnostics(source_name, mir.diagnostics) or has_errors
        if has_errors:
            raise typer.Exit(1)

    @app.command("lir")
    def lir_command(
        target: Annotated[
            str,
            typer.Argument(help="Qy source file to lower into LIR, or - to read from stdin."),
        ],
    ) -> None:
        qy = Qy()
        source, source_name = _read_debug_source(target)
        expansion = qy.macroexpand_source(source, source_name=source_name)
        has_errors = _print_debug_diagnostics(source_name, expansion.diagnostics)
        if expansion.forms:
            program = qy.lower(expansion.forms)
            has_errors = _print_debug_diagnostics(source_name, program.diagnostics) or has_errors
            mir = qy.lower_mir(program)
            has_errors = _print_debug_diagnostics(source_name, mir.diagnostics) or has_errors
            lir = lower_lir(mir)
            typer.echo(dump_lir(lir), nl=False)
            has_errors = _print_debug_diagnostics(source_name, lir.diagnostics) or has_errors
        if has_errors:
            raise typer.Exit(1)

    @app.command("bytecode")
    def bytecode_command(
        target: Annotated[
            str,
            typer.Argument(help="Qy source file to compile, or - to read from stdin."),
        ],
    ) -> None:
        qy = Qy()
        source, source_name = _read_debug_source(target)
        expansion = qy.macroexpand_source(source, source_name=source_name)
        has_errors = _print_debug_diagnostics(source_name, expansion.diagnostics)
        if expansion.forms:
            program = qy.lower(expansion.forms)
            has_errors = _print_debug_diagnostics(source_name, program.diagnostics) or has_errors
            mir = qy.lower_mir(program)
            has_errors = _print_debug_diagnostics(source_name, mir.diagnostics) or has_errors
            bytecode = qy.compile_mir_bytecode(mir)
            typer.echo(dump_bytecode(bytecode), nl=False)
            has_errors = _print_debug_diagnostics(source_name, bytecode.diagnostics) or has_errors
        if has_errors:
            raise typer.Exit(1)

    @app.command("llvm")
    def llvm_command(
        target: Annotated[
            str,
            typer.Argument(help="Qy source file to compile to LLVM IR, or - to read from stdin."),
        ],
    ) -> None:
        from qy.backend.llvm.emit import emit as emit_llvm_module

        qy = Qy()
        source, source_name = _read_debug_source(target)
        expansion = qy.macroexpand_source(source, source_name=source_name)
        has_errors = _print_debug_diagnostics(source_name, expansion.diagnostics)
        if expansion.forms:
            program = qy.lower(expansion.forms)
            has_errors = _print_debug_diagnostics(source_name, program.diagnostics) or has_errors
            mir = qy.lower_mir(program)
            has_errors = _print_debug_diagnostics(source_name, mir.diagnostics) or has_errors
            lir = lower_lir(mir)
            has_errors = _print_debug_diagnostics(source_name, lir.diagnostics) or has_errors
            if lir.ok:
                ll_text = emit_llvm_module(lir)
                typer.echo(ll_text, nl=False)
        if has_errors:
            raise typer.Exit(1)

    # fmt command is registered below via qy.cli.commands.fmt

    @app.command("ast")
    def ast_command(
        path: Annotated[Path, typer.Argument(help="Qy source file to inspect.")],
        raw: Annotated[
            bool,
            typer.Option("--raw", help="Show raw AST without surface dialect expansion."),
        ] = False,
        expand: Annotated[
            bool,
            typer.Option("--expand", help="Show AST after macro expansion."),
        ] = False,
        cst: Annotated[
            bool,
            typer.Option("--cst", help="Show concrete syntax tree (preserves trivia)."),
        ] = False,
    ) -> None:
        source = path.read_text(encoding="utf-8")
        if cst:
            from qy.frontend.reader import parse_cst
            from qy.tools.fmt import dump_cst

            program = parse_cst(source, source_name=str(path))
            typer.echo(dump_cst(program))
        elif raw:
            forms = read_raw(source)
            typer.echo(dump_program(forms))
        elif expand:
            qy = Qy()
            expansion = qy.macroexpand_source(source, source_name=str(path))
            if expansion.forms:
                typer.echo(dump_program(expansion.forms), nl=False)
            if _print_debug_diagnostics(str(path), expansion.diagnostics):
                raise typer.Exit(1)
        else:
            forms = read(source)
            typer.echo(dump_program(forms))

    # check / typecheck commands are registered below via qy.cli.commands.check

    @app.command("operators")
    def operators_command() -> None:
        """列出当前标准库支持的算子."""
        typer.echo(format_operator_docs(), nl=False)

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

    @app.command("export")
    def export_command(
        target: Annotated[
            str,
            typer.Argument(help="Qy source file to compile and export, or - to read from stdin."),
        ],
        output: Annotated[
            str,
            typer.Option("--output", "-o", help="Output file path. Defaults to stdout."),
        ] = "-",
    ) -> None:
        """Export bytecode in JSON interchange format for external VMs."""
        qy = Qy()
        source, source_name = _read_debug_source(target)
        expansion = qy.macroexpand_source(source, source_name=source_name)
        has_errors = _print_debug_diagnostics(source_name, expansion.diagnostics)
        if expansion.forms:
            program = qy.lower(expansion.forms)
            has_errors = _print_debug_diagnostics(source_name, program.diagnostics) or has_errors
            mir = qy.lower_mir(program)
            has_errors = _print_debug_diagnostics(source_name, mir.diagnostics) or has_errors
            bytecode = qy.compile_mir_bytecode(mir)
            has_errors = _print_debug_diagnostics(source_name, bytecode.diagnostics) or has_errors
            json_text = serialize_bytecode_json(bytecode, env=qy.env)
            if output == "-":
                typer.echo(json_text, nl=False)
            else:
                Path(output).write_text(json_text, encoding="utf-8")
                typer.secho(f"exported to {output}", fg=typer.colors.GREEN, err=True)
        if has_errors:
            raise typer.Exit(1)

    # lsp command is registered below via qy.cli.commands.lsp

    from qy.cli.commands import check as check_cmd
    from qy.cli.commands import fmt as fmt_cmd
    from qy.cli.commands import lsp as lsp_cmd
    from qy.cli.commands.pkg import create_pkg_app

    fmt_cmd.register(app)
    check_cmd.register(app)
    lsp_cmd.register(app)
    app.add_typer(create_pkg_app(), name="pkg")

    return app


def repl(qy: Qy) -> int:
    import typer

    _install_repl_readline(qy)
    typer.secho("Qy interactive interpreter", fg=typer.colors.GREEN, bold=True)
    typer.echo("Commands: .help .env .ast <expr> .fmt <expr> .check <expr> .exit")
    while True:
        try:
            source = _read_repl_source()
        except (EOFError, KeyboardInterrupt):
            typer.echo()
            return 0

        source = source.strip()
        if not source:
            continue
        if source in {".exit", ".quit"}:
            return 0
        if source == ".help":
            _print_repl_help()
            continue
        if source == ".env":
            _print_environment(qy)
            continue
        if source.startswith(".ast "):
            _print_repl_ast(source[5:])
            continue
        if source.startswith(".fmt "):
            _print_repl_format(source[5:])
            continue
        if source.startswith(".check "):
            _print_repl_check(source[7:])
            continue

        try:
            for form in read(source):
                typer.echo(format_value(qy.evaluate(form)))
        except QyError as e:
            typer.secho(format_qy_error(e), fg=typer.colors.RED, err=True)


def _read_repl_source() -> str:
    import typer

    return input(f"{typer.style('qy>', fg=typer.colors.BLUE)} ")


def _install_repl_readline(qy: Qy) -> None:
    try:
        import readline
    except ImportError:
        return

    history_path = Path.home() / ".qy_history"
    try:
        readline.read_history_file(history_path)
    except OSError:
        pass
    atexit.register(_write_repl_history, readline, history_path)
    readline.set_completer_delims(" \t\n()\"'")
    readline.set_completer(_repl_completer(qy))
    readline.parse_and_bind("tab: complete")


def _write_repl_history(readline_module: Any, history_path: Path) -> None:
    try:
        readline_module.write_history_file(history_path)
    except OSError:
        pass


def _repl_completer(qy: Qy):
    def complete(text: str, state: int) -> str | None:
        matches = _repl_completions(qy, text)
        try:
            return matches[state]
        except IndexError:
            return None

    return complete


def _repl_completions(qy: Qy, text: str) -> list[str]:
    symbols = [symbol.name for symbol in qy.env.bindings()]
    candidates = (*REPL_COMMANDS, *symbols)
    return sorted(candidate for candidate in candidates if candidate.startswith(text))


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


def _read_debug_source(target: str) -> tuple[str, str]:
    import typer

    try:
        if target == "-":
            return sys.stdin.read(), "<stdin>"
        path = Path(target)
        return path.read_text(encoding="utf-8"), str(path)
    except OSError as e:
        typer.secho(str(e), fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from e


def _print_debug_diagnostics(source_name: str, diagnostics: tuple[Diagnostic, ...]) -> bool:
    import typer

    has_errors = False
    for diagnostic in diagnostics:
        typer.secho(
            _format_diagnostic(source_name, diagnostic),
            fg=_diagnostic_color(diagnostic),
            err=True,
        )
        has_errors = has_errors or diagnostic.severity == "error"
    return has_errors


def _format_diagnostic(path: str | Path, diagnostic: Diagnostic) -> str:
    location = str(path)
    if diagnostic.line is not None and diagnostic.column is not None:
        location = f"{location}:{diagnostic.line}:{diagnostic.column}"
    return f"{location}: {diagnostic.severity}: {diagnostic.message}"


def _diagnostic_color(diagnostic: Diagnostic) -> str:
    import typer

    if diagnostic.severity == "warning":
        return typer.colors.YELLOW
    if diagnostic.severity == "hint":
        return typer.colors.BLUE
    return typer.colors.RED


def _print_repl_help() -> None:
    import typer

    typer.echo("Enter qy expressions to evaluate them in the current session.")
    typer.echo(".env          show bound symbols")
    typer.echo(".ast <expr>   print the parsed syntax tree")
    typer.echo(".fmt <expr>   print canonical qy formatting")
    typer.echo(".check <expr> run analyzer diagnostics")
    typer.echo(".exit         leave the interpreter")


def _print_environment(qy: Qy) -> None:
    import typer

    for symbol in sorted(qy.env.bindings(), key=lambda item: item.name):
        typer.echo(symbol.name)


def _print_repl_ast(source: str) -> None:
    import typer

    try:
        typer.echo(dump_program(read_raw(source)))
    except ReaderSyntaxError as e:
        typer.secho(f"error: {e}", fg=typer.colors.RED, err=True)


def _print_repl_format(source: str) -> None:
    import typer

    try:
        typer.echo(format_source(source), nl=False)
    except ReaderSyntaxError as e:
        typer.secho(f"error: {e}", fg=typer.colors.RED, err=True)


def _print_repl_check(source: str) -> None:
    import typer

    analysis = analyze_source(source)
    if not analysis.diagnostics:
        typer.secho("ok", fg=typer.colors.GREEN)
        return
    for diagnostic in analysis.diagnostics:
        typer.secho(diagnostic.message, fg=_diagnostic_color(diagnostic), err=True)


if __name__ == "__main__":
    raise SystemExit(main())
