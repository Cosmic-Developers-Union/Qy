#!/usr/bin/env python3
# coding: utf-8
"""演示 bytecode 的 dump、pretty print 和二进制序列化功能。."""

from qy.backend.vm import BytecodeFunction
from qy.backend.vm import BytecodeProgram
from qy.backend.vm import Instruction
from qy.backend.vm import deserialize_bytecode
from qy.backend.vm import dump_bytecode
from qy.backend.vm import pretty_print_bytecode
from qy.backend.vm import serialize_bytecode
from qy.frontend.reader import Symbol
from qy.runtime import Qy


def demo_basic_dump():
    """演示基本的 dump 功能。."""
    print("=" * 60)
    print("1. Basic Dump")
    print("=" * 60)

    func = BytecodeFunction(
        name=Symbol("factorial"),
        params=(Symbol("n"),),
        register_count=5,
        instructions=(
            Instruction("LOAD_ENV", (0, Symbol("n"))),
            Instruction("LOAD_HOST", (1, 1)),
            Instruction("CALL", (2, Symbol("<="), 0, 1)),
            Instruction("JUMP_IF_FALSE", (2, 5)),
            Instruction("RETURN", (1,)),
            Instruction("LOAD_ENV", (3, Symbol("n"))),
            Instruction("LOAD_HOST", (4, 1)),
            Instruction("CALL", (3, Symbol("-"), 3, 4)),
            Instruction("CALL", (3, Symbol("factorial"), 3)),
            Instruction("CALL", (0, Symbol("*"), 0, 3)),
            Instruction("RETURN", (0,)),
        ),
    )
    program = BytecodeProgram(functions=(func,), main=0)

    print(dump_bytecode(program))
    print()


def demo_pretty_print():
    """演示 pretty print 功能。."""
    print("=" * 60)
    print("2. Pretty Print")
    print("=" * 60)

    func = BytecodeFunction(
        name=Symbol("add"),
        params=(Symbol("a"), Symbol("b")),
        register_count=3,
        instructions=(
            Instruction("LOAD_ENV", (0, Symbol("a"))),
            Instruction("LOAD_ENV", (1, Symbol("b"))),
            Instruction("CALL", (2, Symbol("+"), 0, 1)),
            Instruction("RETURN", (2,)),
        ),
    )
    program = BytecodeProgram(functions=(func,), main=0)

    print(pretty_print_bytecode(program, show_spans=False))


def demo_binary_serialization():
    """演示二进制序列化和反序列化。."""
    print("=" * 60)
    print("3. Binary Serialization")
    print("=" * 60)

    func = BytecodeFunction(
        name=Symbol("main"),
        params=(),
        register_count=2,
        instructions=(
            Instruction("LOAD_HOST", (0, "Hello, Qy!")),
            Instruction("CALL", (1, Symbol("print"), 0)),
            Instruction("RETURN", (1,)),
        ),
    )
    program = BytecodeProgram(functions=(func,), main=0)

    # Serialize
    binary = serialize_bytecode(program)
    print(f"Serialized size: {len(binary)} bytes")
    print(f"Magic: {binary[:4]!r}")
    print()

    # Deserialize
    restored = deserialize_bytecode(binary)
    print("Deserialized program:")
    print(dump_bytecode(restored))
    print()


def demo_compile_and_dump():
    """演示编译 Qy 代码并 dump bytecode。."""
    print("=" * 60)
    print("4. Compile and Dump")
    print("=" * 60)

    qy = Qy()
    source = """
    (define fib (lambda (n)
      (if (<= n 1)
          n
          (+ (fib (- n 1)) (fib (- n 2))))))
    """

    from qy.async_utils import run_coro
    from qy.build.pipeline import bytecode_artifact
    from qy.build.pipeline import compile_source_to_bytecode_async
    from qy.passes.pass_base import PipelineSession

    session = PipelineSession(env=qy.env)
    result = run_coro(compile_source_to_bytecode_async(source, session))
    bytecode = bytecode_artifact(result)

    print("Source:")
    print(source)
    print("\nBytecode:")
    print(dump_bytecode(bytecode))
    print()


def main():
    """运行所有演示。."""
    demo_basic_dump()
    demo_pretty_print()
    demo_binary_serialization()
    demo_compile_and_dump()


if __name__ == "__main__":
    main()
