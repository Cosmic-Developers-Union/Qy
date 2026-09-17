// 符号空间（symbol-space）与字面量解析。
//
// 真源：
//   - `qy/session/runtime_space.py`（RuntimeSpace：resolve / define / child）
//   - `qy/session/pre_ss.py`（lisp-ss / number-ss / char-ss / string-ss 与
//     `try_default_literal` / `parse_number_literal` / `parse_string_literal` /
//     `parse_char_literal`）
//
// 结构：每个 `Env` 就是一个 symbol-space，`parent` 是链上的下一个空间。
// resolve 先做链 walk，全链 miss 之后才走字面量解析 —— 与 Python
// `RuntimeSpace.resolve`（链 miss → profile literal fallback）一致。
//
// 注意：ASCII 数字/字符串/字符的解析结果必须是 Qy 语义值
// （IntValue / FloatValue / StringValue / CharValue），不能是宿主原语。

import { MISSING } from './internal.ts';
import { QyResolveError } from './errors.ts';
import {
  Chain,
  CharValue,
  FloatValue,
  IntValue,
  QY_NIL,
  QY_NONE,
  QY_T,
  StringValue,
  Symbol,
  type QyValue,
} from './values.ts';

// ---------------------------------------------------------------------------
// 字面量解析（qy/session/pre_ss.py）
// ---------------------------------------------------------------------------

const CHAR_NAMED: Record<string, string> = {
  space: ' ',
  newline: '\n',
  tab: '\t',
  return: '\r',
  null: '\u0000',
  nul: '\u0000',
  backspace: '\b',
  delete: '\u007f',
  escape: '\u001b',
  alarm: '\u0007',
  vtab: '\u000b',
  formfeed: '\f',
};

export function isStringLiteral(name: string): boolean {
  return name.startsWith('"') || name.startsWith('r"');
}

export function isCharLiteral(name: string): boolean {
  return name.startsWith('#\\') && name.length > 2;
}

export function isNumberLiteral(name: string): boolean {
  return parseIntLiteral(name) !== undefined || parseFloatLiteral(name) !== undefined;
}

/**
 * Python `int(name)`（base 10）的对应实现。
 *
 * 注意 Python 的 `int()` 默认进制不接受 `0x`/`0o`/`0b` 前缀，所以 Qy 的
 * number-ss 也不把 `0x10` 当字面量（`parse_number_literal` 会返回 MISSING）。
 */
export function parseIntLiteral(name: string): number | undefined {
  const text = name.trim();
  if (text === '') return undefined;
  if (!/^[+-]?\d(?:_?\d)*$/.test(text)) return undefined;
  const parsed = Number.parseInt(text.replace(/_/g, ''), 10);
  return Number.isNaN(parsed) ? undefined : parsed;
}

/**
 * Python `float(name)` 的近似实现。
 * 与 Python 一样拒绝 inf / nan（`parse_number_literal` 显式过滤）。
 */
export function parseFloatLiteral(name: string): number | undefined {
  const text = name.trim();
  if (text === '') return undefined;
  if (!/^[+-]?(\d(?:_?\d)*)?(\.(\d(?:_?\d)*)?)?([eE][+-]?\d(?:_?\d)*)?$/.test(text)) return undefined;
  if (!/\d/.test(text)) return undefined;
  const parsed = Number(text.replace(/_/g, ''));
  if (Number.isNaN(parsed) || !Number.isFinite(parsed)) return undefined;
  return parsed;
}

/** 字符字面量解析；失败返回 MISSING。 */
export function parseCharLiteral(name: string): QyValue {
  if (!isCharLiteral(name)) return MISSING;
  const body = name.slice(2);
  if (body.length === 1) return new CharValue(body);
  const lower = body.toLowerCase();
  if (lower in CHAR_NAMED) return new CharValue(CHAR_NAMED[lower]);
  if (lower.startsWith('u') && (body.length === 5 || body.length === 9)) {
    const code = Number.parseInt(body.slice(1), 16);
    if (Number.isFinite(code) && code <= 0x10ffff) return new CharValue(String.fromCodePoint(code));
    return MISSING;
  }
  if (lower.startsWith('x') && body.length === 3) {
    const code = Number.parseInt(body.slice(1), 16);
    if (Number.isFinite(code)) return new CharValue(String.fromCodePoint(code));
    return MISSING;
  }
  return MISSING;
}

/**
 * Python 字符串字面量解析（`ast.literal_eval` 的对应）。
 * 支持 `"..."` 与 `r"..."`，以及常规转义 \\n \\t \\r \\\\ \\" \\' \\xNN \\uNNNN
 * \\UNNNNNNNN \\0 \\a \\b \\f \\v。
 */
export function parseStringLiteral(name: string): QyValue {
  let raw = false;
  let body: string;
  if (name.startsWith('r"')) {
    raw = true;
    body = name.slice(2);
  } else if (name.startsWith('"')) {
    body = name.slice(1);
  } else {
    return MISSING;
  }
  if (!body.endsWith('"')) return MISSING;
  body = body.slice(0, -1);

  let out = '';
  for (let i = 0; i < body.length; i += 1) {
    const char = body[i];
    if (char !== '\\' || raw) {
      out += char;
      continue;
    }
    i += 1;
    if (i >= body.length) return MISSING;
    const esc = body[i];
    switch (esc) {
      case 'n':
        out += '\n';
        break;
      case 't':
        out += '\t';
        break;
      case 'r':
        out += '\r';
        break;
      case '\\':
        out += '\\';
        break;
      case "'":
        out += "'";
        break;
      case '"':
        out += '"';
        break;
      case 'a':
        out += '\u0007';
        break;
      case 'b':
        out += '\b';
        break;
      case 'f':
        out += '\f';
        break;
      case 'v':
        out += '\u000b';
        break;
      case '0':
        out += '\u0000';
        break;
      case 'x': {
        const hex = body.slice(i + 1, i + 3);
        if (!/^[0-9a-fA-F]{2}$/.test(hex)) return MISSING;
        out += String.fromCharCode(Number.parseInt(hex, 16));
        i += 2;
        break;
      }
      case 'u': {
        const hex = body.slice(i + 1, i + 5);
        if (!/^[0-9a-fA-F]{4}$/.test(hex)) return MISSING;
        out += String.fromCharCode(Number.parseInt(hex, 16));
        i += 4;
        break;
      }
      case 'U': {
        const hex = body.slice(i + 1, i + 9);
        if (!/^[0-9a-fA-F]{8}$/.test(hex)) return MISSING;
        out += String.fromCodePoint(Number.parseInt(hex, 16));
        i += 8;
        break;
      }
      default:
        // Python 会保留未知转义的反斜杠
        out += `\\${esc}`;
        break;
    }
  }
  return new StringValue(out);
}

/**
 * `qy/session/pre_ss.py::try_default_literal` 的对应实现。
 * 无法解析为字面量时返回 MISSING。
 */
export function tryDefaultLiteral(symbol: Symbol): QyValue {
  const name = symbol.name;
  if (name === 'T' || name === 'true') return QY_T;
  if (name === 'nil' || name === 'false') return QY_NIL;
  if (name === 'none') return QY_NONE;

  if (isCharLiteral(name)) {
    const result = parseCharLiteral(name);
    if (result !== MISSING) return result;
  }
  if (isStringLiteral(name)) {
    const result = parseStringLiteral(name);
    if (result !== MISSING) return result;
  }
  const intValue = parseIntLiteral(name);
  if (intValue !== undefined) return new IntValue(intValue);
  const floatValue = parseFloatLiteral(name);
  if (floatValue !== undefined) return new FloatValue(floatValue);
  return MISSING;
}

/** `default_literal_type` 的对应实现；不是字面量时返回 null。 */
export function defaultLiteralType(name: string): string | null {
  if (isStringLiteral(name)) return 'string';
  if (isCharLiteral(name)) {
    return parseCharLiteral(name) !== MISSING ? 'char' : null;
  }
  const value = tryDefaultLiteral(new Symbol(name));
  if (value === MISSING) return null;
  if (value === QY_NIL) return 'nil';
  if (value === QY_T) return 'T';
  if (value === QY_NONE) return 'none';
  if (value instanceof IntValue || value instanceof FloatValue) return 'number';
  return null;
}

// ---------------------------------------------------------------------------
// symbol-space
// ---------------------------------------------------------------------------

/** 一个 symbol-space（作用域）。 */
export class Env {
  private readonly bindings: Map<string, QyValue>;

  constructor(
    parent: Env | null = null,
    bindings?: Map<string, QyValue>,
    readonly name = '',
  ) {
    this.parent = parent;
    this.bindings = bindings ?? new Map<string, QyValue>();
  }

  readonly parent: Env | null;

  /** 新建子空间（`let` / `lambda` / `module` / 函数调用帧都走它）。 */
  child(bindings?: Map<string, QyValue>): Env {
    return new Env(this, bindings, '');
  }

  /** 当前空间内的绑定快照（对应 `local_bindings`）。 */
  localBindings(): Map<string, QyValue> {
    return new Map(this.bindings);
  }

  hasLocal(name: string): boolean {
    return this.bindings.has(name);
  }

  /** `define`：允许重绑定当前空间内的名字，对应 `SymbolSpace.define`。 */
  define(name: string, value: QyValue): QyValue {
    this.bindings.set(name, value);
    return value;
  }

  /** `define_once`：当前空间已绑定则报错，对应 `SymbolSpace.define_once`。 */
  defineOnce(name: string, value: QyValue): QyValue {
    if (this.bindings.has(name)) {
      throw new QyResolveError(`symbol '${name}' is already bound in this scope; use 'let' to shadow`);
    }
    this.bindings.set(name, value);
    return value;
  }

  /** 单层查找（对应 `SymbolSpace.lookup`，不递归 parent）。 */
  lookupLocal(symbol: Symbol): QyValue {
    return this.bindings.has(symbol.name) ? (this.bindings.get(symbol.name) as QyValue) : MISSING;
  }

  /** 沿链查找，不落到字面量解析（对应 `SymbolSpace.resolve`）。 */
  resolveRaw(symbol: Symbol): QyValue {
    let current: Env | null = this;
    while (current !== null) {
      const value = current.lookupLocal(symbol);
      if (value !== MISSING) return value;
      current = current.parent;
    }
    return MISSING;
  }

  /**
   * 完整解析：链 walk 命中即返回；全链 miss 后回退到字面量解析。
   * 解析失败抛 `QyResolveError`（对应 `resolve_default_literal`）。
   */
  resolve(symbol: Symbol): QyValue {
    const value = this.resolveRaw(symbol);
    if (value !== MISSING) return value;
    const literal = tryDefaultLiteral(symbol);
    if (literal !== MISSING) return literal;
    throw new QyResolveError(`unresolved symbol '${symbol.name}'`);
  }
}

/** 便捷构造：从普通对象建立一个空间。 */
export function envWith(bindings: Record<string, QyValue>, parent: Env | null = null, name = ''): Env {
  return new Env(parent, new Map(Object.entries(bindings)), name);
}

export { QY_NIL, QY_T, QY_NONE, Chain, Symbol };
