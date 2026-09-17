// 值的文本表示，必须与 Python 侧 `qy/display.py::format_value` 逐字节一致。
//
// 对应关系：
//   nil → "nil"；T → "T"；none → "none"
//   NumberValue → str(value)（整数十进制；浮点用 Python 的 repr 规则）
//   StringValue → 原始文本（不加引号）
//   Chain → "(a b c)" / "(a b . c)"
//   TupleValue → "(a b)"；ListValue → "[a b]"；DictValue → "{k v}"；SetValue → "#{...}"
//   Symbol → reader 的 write（必要时 JSON 转义）

import {
  ArrayValue,
  Chain,
  CharValue,
  Continuation,
  DictValue,
  EffectDefinition,
  HashMapValue,
  ListValue,
  ModuleValue,
  NumberValue,
  PureOperatorValue,
  QY_NIL,
  QY_NONE,
  QY_T,
  RawOperatorValue,
  SetValue,
  StringValue,
  Symbol,
  TupleValue,
  type QyValue,
} from './values.ts';
import { BytecodeFunctionValue } from './frame.ts';

/**
 * Python `str(float)` / `repr(float)` 的近似实现。
 *
 * Python 的浮点 repr 是「最短可回环」表示，且：
 * - 整数浮点必须带 `.0`（`4.0`）；
 * - 指数形式出现在 exp < -4 或 exp >= 16；
 * - 指数至少两位（`1e-07`）。
 * JS 的 `Number.prototype.toString` 也是最短回环，但阈值与 `.0` 规则不同，
 * 所以这里以 `toExponential()` 的最短数字序列为基准重新排版。
 */
export function pyFloatRepr(x: number): string {
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

  let intPart: string;
  let fracPart: string;
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

function encodeSymbol(name: string): string {
  if (!name) return JSON.stringify(name);
  for (const char of name) {
    if (/\s/.test(char) || '()"\';'.includes(char)) {
      return JSON.stringify(name);
    }
  }
  return name;
}

/** Symbol 的 write 形式（字符串字面量符号原样输出）。 */
export function writeSymbol(value: Symbol): string {
  if (value.name.startsWith('"') || value.name.startsWith('r"')) return value.name;
  return encodeSymbol(value.name);
}

function formatCons(value: Chain): string {
  const parts: string[] = [];
  let current: QyValue = value;
  while (current instanceof Chain) {
    parts.push(formatValue(current.head));
    current = current.tail;
  }
  if (current === QY_NIL) {
    return `(${parts.join(' ')})`;
  }
  return `(${parts.join(' ')} . ${formatValue(current)})`;
}

/** Python `repr(str)` 的近似（单引号优先，与 dataclass repr 一致）。 */
function pyReprString(value: string): string {
  if (!value.includes("'") || value.includes('"')) {
    return `'${value.replace(/\\/g, '\\\\').replace(/\n/g, '\\n').replace(/\t/g, '\\t').replace(/'/g, "\\'")}'`;
  }
  return `"${value.replace(/\\/g, '\\\\').replace(/"/g, '\\"')}"`;
}

/** 与 `qy/display.py::format_value` 对应的格式化入口。 */
export function formatValue(value: QyValue): string {
  if (value === QY_NIL) return 'nil';
  if (value === QY_T) return 'T';
  if (value === QY_NONE) return 'none';
  if (value instanceof NumberValue) {
    return value.isInteger ? String(value.value) : pyFloatRepr(value.value);
  }
  if (value instanceof StringValue) return value.value;
  if (value instanceof Chain) return formatCons(value);
  if (value instanceof TupleValue) {
    return `(${value.items.map(formatValue).join(' ')})`;
  }
  if (value instanceof ListValue) {
    return `[${value.items.map(formatValue).join(' ')}]`;
  }
  if (value instanceof DictValue) {
    const items = value.entries.map(([key, item]) => `${formatValue(key)} ${formatValue(item)}`);
    return `{${items.join(' ')}}`;
  }
  if (value instanceof SetValue) {
    const items = value.items.map(formatValue).sort();
    return `#{${items.join(' ')}}`;
  }
  if (value instanceof HashMapValue) {
    const items = value.entries.map(([key, item]) => `${formatValue(key)} ${formatValue(item)}`);
    return `{${items.join(' ')}}`;
  }
  if (value instanceof ArrayValue) {
    return `[${value.items.map(formatValue).join(' ')}]`;
  }
  if (value instanceof Symbol) return writeSymbol(value);
  // Python `format_value` 没有为 CharValue 分支，落到末尾的 `repr(value)`。
  if (value instanceof CharValue) return `CharValue(value=${pyReprString(value.value)})`;
  if (typeof value === 'boolean') return value ? 'true' : 'false';
  if (value === null || value === undefined) return 'none';
  if (typeof value === 'number') return Number.isInteger(value) ? String(value) : pyFloatRepr(value);
  if (Array.isArray(value)) return `[${value.map(formatValue).join(' ')}]`;
  if (value instanceof BytecodeFunctionValue) {
    return `<function ${value.fn.name}>`;
  }
  if (value instanceof PureOperatorValue || value instanceof RawOperatorValue) {
    return `<operator ${value.name}>`;
  }
  if (value instanceof EffectDefinition) return `<effect ${value.name}>`;
  if (value instanceof Continuation) return '<continuation>';
  if (value instanceof ModuleValue) return `<module ${value.name}>`;
  return String(value);
}

/**
 * `qy/cli/_common.py::_is_definition_artifact` 的对应实现：
 * 这些值由绑定形式求值产生，不是用户可见表达式值，`qy run` 不打印。
 */
export function isDefinitionArtifact(value: QyValue): boolean {
  if (value === null || value === undefined) return true;
  if (value instanceof BytecodeFunctionValue) return true;
  if (value instanceof ModuleValue) return true;
  if (value instanceof EffectDefinition) return true;
  // MacroDefinition 在字节码层只以 COMPILE_TIME_MACRO 占位符出现，已被 APPEND_RESULT
  // 归一为 null；此处无需再判。
  return false;
}
