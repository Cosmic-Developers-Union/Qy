# coding: utf-8

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import cast

from qy.analyzer import Diagnostic
from qy.analyzer import analyze_source
from qy.evaluator import EvaluationError
from qy.formatter import dump_program
from qy.formatter import format_source
from qy.reader import ReaderSyntaxError
from qy.reader import Symbol
from qy.reader import TupleForm
from qy.reader import read
from qy.reader import write_tuple
from qy.runtime import Qy


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        return repl(Qy())

    command = argv[0]
    if command == "lsp":
        from qy.lsp import main as lsp_main

        return lsp_main()
    if command == "fmt":
        return format_command(argv[1:])
    if command == "ast":
        return ast_command(argv[1:])
    if command in {"check", "typecheck"}:
        return check_command(argv[1:])

    value = Qy().evaluate_file(Path(command))
    print(format_value(value))
    return 0


def format_command(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="qy fmt")
    parser.add_argument("-w", "--write", action="store_true", help="rewrite the file in place")
    parser.add_argument("path")
    args = parser.parse_args(argv)

    path = Path(args.path)
    formatted = format_source(path.read_text(encoding="utf-8"))
    if args.write:
        path.write_text(formatted, encoding="utf-8")
    else:
        print(formatted, end="")
    return 0


def ast_command(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="qy ast")
    parser.add_argument("path")
    args = parser.parse_args(argv)

    path = Path(args.path)
    print(dump_program(read(path.read_text(encoding="utf-8"))))
    return 0


def check_command(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="qy check")
    parser.add_argument("path")
    args = parser.parse_args(argv)

    path = Path(args.path)
    analysis = analyze_source(path.read_text(encoding="utf-8"))
    for diagnostic in analysis.diagnostics:
        print(_format_diagnostic(path, diagnostic), file=sys.stderr)
    return 0 if analysis.ok else 1


def repl(qy: Qy) -> int:
    print("Qy interactive interpreter. Type .exit to quit.")
    while True:
        try:
            source = input("qy> ")
        except EOFError:
            print()
            return 0
        if source.strip() in {".exit", ".quit"}:
            return 0
        if not source.strip():
            continue
        try:
            for form in read(source):
                print(format_value(qy.evaluate(form)))
        except (EvaluationError, ReaderSyntaxError) as e:
            print(f"error: {e}", file=sys.stderr)


def format_value(value: object) -> str:
    if isinstance(value, Symbol | tuple | int | float | bool) or value is None:
        try:
            return write_tuple(cast(TupleForm, value))
        except TypeError:
            pass
    return repr(value)


def _format_diagnostic(path: Path, diagnostic: Diagnostic) -> str:
    location = str(path)
    if diagnostic.line is not None and diagnostic.column is not None:
        location = f"{location}:{diagnostic.line}:{diagnostic.column}"
    return f"{location}: {diagnostic.severity}: {diagnostic.message}"


if __name__ == "__main__":
    raise SystemExit(main())
