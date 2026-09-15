'use strict';
/*
 * Qy WebAssembly host runtime.
 *
 * Implements the "qy" import namespace used by backend/wasm/emit.py:
 *   call_builtin(idx: i64, argc: i32, argv: i32) -> i64
 *   append_result(value: i64) -> ()
 *
 * Value encoding matches backend/wasm/abi.py: i64 with a low 3-bit tag.
 *
 * Usage:
 *   node runtime.js program.wasm
 */

import fs from 'node:fs';
import { pathToFileURL } from 'node:url';

const TAG_INT = 0n;
const TAG_NIL = 1n;
const TAG_T = 2n;
const TAG_CHAR = 3n;
const TAG_CALLABLE = 4n;
const TAG_STRING = 5n;
const TAG_MASK = 7n;

const NIL = TAG_NIL;
const T = TAG_T;

class QyRuntimeError extends Error {}

function tagOf(value) {
  return value & TAG_MASK;
}

function asInt(value) {
  return BigInt.asIntN(64, value) >> 3n;
}

function encodeInt(value) {
  return (value << 3n) | TAG_INT;
}

function createHost() {
  let memory = null;
  const results = [];
  const decoder = new TextDecoder('utf-8');

  const view = () => new DataView(memory.buffer);

  function argvAt(pointer, index) {
    return view().getBigInt64(pointer + index * 8, true);
  }

  function readString(value) {
    const address = Number(BigInt.asUintN(64, value) >> 3n);
    const length = view().getInt32(address, true);
    const bytes = new Uint8Array(memory.buffer, address + 4, length);
    return decoder.decode(bytes);
  }

  function format(value) {
    switch (tagOf(value)) {
      case TAG_INT:
        return asInt(value).toString();
      case TAG_NIL:
        return 'nil';
      case TAG_T:
        return 'T';
      case TAG_CHAR:
        return String.fromCodePoint(Number(BigInt.asUintN(64, value) >> 3n));
      case TAG_STRING:
        return readString(value);
      case TAG_CALLABLE:
        return '<function>';
      default:
        return '<value>';
    }
  }

  function requireInt(value) {
    if (tagOf(value) !== TAG_INT) {
      throw new QyRuntimeError('expected number, got ' + format(value));
    }
    return asInt(value);
  }

  function boolean(condition) {
    return condition ? T : NIL;
  }

  // Index order must match backend/wasm/abi.py BUILTIN_NAMES.
  const builtins = [
    /*  0 + */ (args) => encodeInt(requireInt(args[0]) + requireInt(args[1])),
    /*  1 - */ (args) => encodeInt(requireInt(args[0]) - requireInt(args[1])),
    /*  2 * */ (args) => encodeInt(requireInt(args[0]) * requireInt(args[1])),
    /*  3 / */ (args) => {
      const divisor = requireInt(args[1]);
      if (divisor === 0n) throw new QyRuntimeError('divide by zero');
      return encodeInt(requireInt(args[0]) / divisor);
    },
    /*  4 = */ (args) => boolean(args[0] === args[1]),
    /*  5 eq */ (args) => boolean(args[0] === args[1]),
    /*  6 < */ (args) => boolean(requireInt(args[0]) < requireInt(args[1])),
    /*  7 > */ (args) => boolean(requireInt(args[0]) > requireInt(args[1])),
    /*  8 display */ (args) => {
      process.stdout.write(format(args[0]));
      return NIL;
    },
    /*  9 echo */ (args) => {
      process.stdout.write(format(args[0]) + '\n');
      return NIL;
    },
    /* 10 newline */ () => {
      process.stdout.write('\n');
      return NIL;
    },
    /* 11 read */ () => NIL,
    /* 12 read-int */ () => NIL,
    /* 13 cons */ () => {
      throw new QyRuntimeError('cons is not supported by the wasm host yet');
    },
    /* 14 car */ () => {
      throw new QyRuntimeError('car is not supported by the wasm host yet');
    },
    /* 15 cdr */ () => {
      throw new QyRuntimeError('cdr is not supported by the wasm host yet');
    },
    /* 16 nil? */ (args) => boolean(tagOf(args[0]) === TAG_NIL),
    /* 17 not */ (args) => boolean(args[0] === NIL),
  ];

  const imports = {
    qy: {
      call_builtin(index, argc, pointer) {
        const args = [];
        for (let i = 0; i < Number(argc); i += 1) {
          args.push(argvAt(pointer, i));
        }
        const builtin = builtins[Number(index)];
        if (!builtin) {
          throw new QyRuntimeError('unknown builtin index ' + index);
        }
        return builtin(args);
      },
      append_result(value) {
        results.push(value);
      },
    },
  };

  return {
    imports,
    results,
    format,
    setMemory(instanceMemory) {
      memory = instanceMemory;
    },
  };
}

async function instantiate(bytes) {
  const host = createHost();
  const { instance } = await WebAssembly.instantiate(bytes, host.imports);
  host.setMemory(instance.exports.memory);
  return { instance, host };
}

async function runFile(wasmPath) {
  const bytes = fs.readFileSync(wasmPath);
  const { instance, host } = await instantiate(bytes);
  instance.exports.main(0, 0);
  return host.results.map((value) => host.format(value));
}

export { createHost, instantiate, runFile, QyRuntimeError };

const isMain =
  process.argv[1] !== undefined && import.meta.url === pathToFileURL(process.argv[1]).href;

if (isMain) {
  const wasmPath = process.argv[2];
  if (!wasmPath) {
    process.stderr.write('usage: node runtime.js <program.wasm>\n');
    process.exit(2);
  }
  runFile(wasmPath)
    .then((lines) => {
      if (lines.length > 0) {
        process.stdout.write(lines.join('\n') + '\n');
      }
    })
    .catch((error) => {
      process.stderr.write(String(error && error.stack ? error.stack : error) + '\n');
      process.exit(1);
    });
}
