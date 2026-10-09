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
const TAG_FLOAT = 6n;
const TAG_HEAP = 7n;
const TAG_MASK = 7n;

// heap 对象（symbol / cons / float 结果）在 linear memory 的 bump arena（[2 MiB, 4 MiB)）。
const HEAP_ARENA_BASE = 2 << 20;
// heap 对象子 tag（首 i32）。
const HEAP_SYMBOL = 1;
const HEAP_CONS = 2;

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

/**
 * Python `repr(float)` 的近似实现（与 TS 宿主 `pyFloatRepr` 一致）。
 *
 * - 整数浮点必须带 `.0`；
 * - 指数形式出现在 exp < -4 或 exp >= 16；
 * - 指数至少两位（`1e-07`）。
 */
function pyFloatRepr(x) {
  if (Number.isNaN(x)) return 'nan';
  if (x === Number.POSITIVE_INFINITY) return 'inf';
  if (x === Number.NEGATIVE_INFINITY) return '-inf';
  if (x === 0) return Object.is(x, -0) ? '-0.0' : '0.0';

  const exponential = x.toExponential();
  const match = /^(-?)(\d)(?:\.(\d+))?e([+-]\d+)$/.exec(exponential);
  if (!match) return String(x);
  const sign = match[1];
  const digits = match[2] + (match[3] ?? '');
  const exp = Number.parseInt(match[4], 10);

  if (exp < -4 || exp >= 16) {
    const mantissa = digits.length > 1 ? `${digits[0]}.${digits.slice(1)}` : digits;
    const expSign = exp >= 0 ? '+' : '-';
    return `${sign}${mantissa}e${expSign}${String(Math.abs(exp)).padStart(2, '0')}`;
  }

  let intPart;
  let fracPart;
  if (exp >= 0) {
    if (digits.length > exp + 1) {
      intPart = digits.slice(0, exp + 1);
      fracPart = digits.slice(exp + 1);
    } else {
      intPart = digits + '0'.repeat(exp + 1 - digits.length);
      fracPart = '';
    }
  } else {
    intPart = '0';
    fracPart = '0'.repeat(-exp - 1) + digits;
  }
  if (fracPart === '') fracPart = '0';
  return `${sign}${intPart}.${fracPart}`;
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

  let heapArena = HEAP_ARENA_BASE;

  function allocHeap(size) {
    const address = heapArena;
    heapArena += size;
    if (heapArena > memory.buffer.byteLength) {
      throw new QyRuntimeError('wasm heap arena exhausted');
    }
    return address;
  }

  function heapOffset(value) {
    return Number(BigInt.asUintN(64, value) >> 3n);
  }

  function heapTagOf(value) {
    return view().getInt32(heapOffset(value), true);
  }

  function isHeap(value, tag) {
    return tagOf(value) === TAG_HEAP && heapTagOf(value) === tag;
  }

  function readFloat(value) {
    return view().getFloat64(heapOffset(value), true);
  }

  function makeFloat(x) {
    const address = allocHeap(8);
    view().setFloat64(address, x, true);
    return (BigInt(address) << 3n) | TAG_FLOAT;
  }

  function stringAt(stringOffset) {
    const length = view().getInt32(stringOffset, true);
    const bytes = new Uint8Array(memory.buffer, stringOffset + 4, length);
    return decoder.decode(bytes);
  }

  function readSymbol(value) {
    return stringAt(view().getInt32(heapOffset(value) + 4, true));
  }

  function makeCons(car, cdr) {
    const address = allocHeap(24);
    view().setInt32(address, HEAP_CONS, true);
    view().setBigInt64(address + 8, BigInt.asIntN(64, car), true);
    view().setBigInt64(address + 16, BigInt.asIntN(64, cdr), true);
    return (BigInt(address) << 3n) | TAG_HEAP;
  }

  function carOf(value) {
    if (tagOf(value) === TAG_NIL) return NIL;
    if (!isHeap(value, HEAP_CONS)) {
      throw new QyRuntimeError('car expects a chain, got ' + format(value));
    }
    return view().getBigInt64(heapOffset(value) + 8, true);
  }

  function cdrOf(value) {
    if (tagOf(value) === TAG_NIL) return NIL;
    if (!isHeap(value, HEAP_CONS)) {
      throw new QyRuntimeError('cdr expects a chain, got ' + format(value));
    }
    return view().getBigInt64(heapOffset(value) + 16, true);
  }

  function formatHeap(value) {
    if (isHeap(value, HEAP_SYMBOL)) return readSymbol(value);
    if (isHeap(value, HEAP_CONS)) {
      const parts = [];
      let current = value;
      while (tagOf(current) === TAG_HEAP && heapTagOf(current) === HEAP_CONS) {
        parts.push(format(view().getBigInt64(heapOffset(current) + 8, true)));
        current = view().getBigInt64(heapOffset(current) + 16, true);
      }
      if (tagOf(current) !== TAG_NIL) {
        return '(' + parts.join(' ') + ' . ' + format(current) + ')';
      }
      return '(' + parts.join(' ') + ')';
    }
    return '<heap>';
  }

  function isFloat(value) {
    return tagOf(value) === TAG_FLOAT;
  }

  function asNumber(value) {
    return isFloat(value) ? readFloat(value) : Number(requireInt(value));
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
      case TAG_FLOAT:
        return pyFloatRepr(readFloat(value));
      case TAG_HEAP:
        return formatHeap(value);
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
    /*  0 + */ (args) =>
      isFloat(args[0]) || isFloat(args[1])
        ? makeFloat(asNumber(args[0]) + asNumber(args[1]))
        : encodeInt(requireInt(args[0]) + requireInt(args[1])),
    /*  1 - */ (args) =>
      isFloat(args[0]) || isFloat(args[1])
        ? makeFloat(asNumber(args[0]) - asNumber(args[1]))
        : encodeInt(requireInt(args[0]) - requireInt(args[1])),
    /*  2 * */ (args) =>
      isFloat(args[0]) || isFloat(args[1])
        ? makeFloat(asNumber(args[0]) * asNumber(args[1]))
        : encodeInt(requireInt(args[0]) * requireInt(args[1])),
    /*  3 / */ (args) => {
      if (isFloat(args[0]) || isFloat(args[1])) {
        const floatDivisor = asNumber(args[1]);
        if (floatDivisor === 0) throw new QyRuntimeError('divide by zero');
        return makeFloat(asNumber(args[0]) / floatDivisor);
      }
      const divisor = requireInt(args[1]);
      if (divisor === 0n) throw new QyRuntimeError('divide by zero');
      return encodeInt(requireInt(args[0]) / divisor);
    },
    /*  4 = */ (args) =>
      isFloat(args[0]) || isFloat(args[1])
        ? boolean(asNumber(args[0]) === asNumber(args[1]))
        : boolean(args[0] === args[1]),
    /*  5 eq */ (args) => boolean(args[0] === args[1]),
    /*  6 < */ (args) =>
      isFloat(args[0]) || isFloat(args[1])
        ? boolean(asNumber(args[0]) < asNumber(args[1]))
        : boolean(requireInt(args[0]) < requireInt(args[1])),
    /*  7 > */ (args) =>
      isFloat(args[0]) || isFloat(args[1])
        ? boolean(asNumber(args[0]) > asNumber(args[1]))
        : boolean(requireInt(args[0]) > requireInt(args[1])),
    /*  8 display */ (args) => {
      process.stdout.write(format(args[0]));
      return args[0];
    },
    /*  9 echo */ (args) => {
      process.stdout.write(format(args[0]) + '\n');
      return args[0];
    },
    /* 10 newline */ () => {
      process.stdout.write('\n');
      return NIL;
    },
    /* 11 read */ () => NIL,
    /* 12 read-int */ () => NIL,
    /* 13 cons */ (args) => makeCons(args[0], args[1]),
    /* 14 car */ (args) => carOf(args[0]),
    /* 15 cdr */ (args) => cdrOf(args[0]),
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

function isDefinitionArtifact(value) {
  // 与 Python `qy/cli/_common.py::_is_definition_artifact` / TS `qyvm` /
  // Go `IsDefinitionArtifact` 对齐：函数（wasm 中唯一的 definition 值）
  // 不作为顶层结果打印。
  return tagOf(value) === TAG_CALLABLE;
}

async function runFile(wasmPath) {
  const bytes = fs.readFileSync(wasmPath);
  const { instance, host } = await instantiate(bytes);
  instance.exports.main(0, 0);
  return host.results
    .filter((value) => !isDefinitionArtifact(value))
    .map((value) => host.format(value));
}

export { createHost, instantiate, isDefinitionArtifact, runFile, QyRuntimeError };

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
