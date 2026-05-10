# coding: utf-8

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import cast

from qy.evaluator import Environment
from qy.evaluator import EvaluationError
from qy.evaluator import evaluate
from qy.evaluator import evaluate_file
from qy.evaluator import standard_environment
from qy.reader import ReaderSyntaxError
from qy.reader import Symbol
from qy.reader import TupleForm
from qy.reader import read
from qy.reader import write_tuple


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="qy")
    parser.add_argument("target", nargs="?", help="qy source file, or 'lsp' to start the LSP")
    args = parser.parse_args(argv)

    if args.target == "lsp":
        from qy.lsp import main as lsp_main

        return lsp_main()
    if args.target:
        value = evaluate_file(Path(args.target))
        print(format_value(value))
        return 0
    return repl()


def repl(env: Environment | None = None) -> int:
    env = env or standard_environment()
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
                print(format_value(evaluate(form, env)))
        except (EvaluationError, ReaderSyntaxError) as e:
            print(f"error: {e}", file=sys.stderr)


def format_value(value: object) -> str:
    if isinstance(value, Symbol | tuple | int | float | bool) or value is None:
        try:
            return write_tuple(cast(TupleForm, value))
        except TypeError:
            pass
    return repr(value)


if __name__ == "__main__":
    raise SystemExit(main())
