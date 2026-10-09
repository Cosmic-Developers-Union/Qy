// `qy.io` 模块与输出原语。
//
// 真源：`qy/std/io.py`（`print` / `echo` 是 EffectOperator，参数为 raw）。
//
// `_print` 的关键行为：**只**把仍是 Symbol 的字面量拼写解析为值，绝不重新求值
// 已求好的 runtime value（否则 cons 结果会被当作调用执行）。

import { defaultLiteralType, tryDefaultLiteral } from '../environment.ts';
import { MISSING } from '../internal.ts';
import { formatValue } from '../display.ts';
import { QY_NIL, Symbol, type QyValue } from '../values.ts';

/** 输出回调；默认写 stdout，嵌入方可覆盖（例如捕获为字符串）。 */
export type OutputWriter = (text: string) => void;

let writer: OutputWriter = (text: string) => {
  const proc = (globalThis as { process?: { stdout?: { write(data: string): void } } }).process;
  if (proc?.stdout) proc.stdout.write(text);
};

/** 替换输出回调（用于宿主嵌入与测试）。 */
export function setOutputWriter(next: OutputWriter): void {
  writer = next;
}

/** 取当前输出回调。 */
export function getOutputWriter(): OutputWriter {
  return writer;
}

function resolveLiteral(value: QyValue, env: QyValue): QyValue {
  if (value instanceof Symbol) {
    if (defaultLiteralType(value.name) === null) return value;
    const literal = tryDefaultLiteral(value);
    if (literal !== MISSING) return literal;
    return value;
  }
  void env;
  return value;
}

/** `print` / `echo` 的实现体（`io.py::_print`）。 */
export function printOp(args: QyValue[], env: QyValue): QyValue {
  const values = args.map((arg) => resolveLiteral(arg, env));
  writer(`${values.map(formatValue).join(' ')}\n`);
  return values.length === 0 ? null : values[values.length - 1];
}

/** `display`：输出但不追加换行（与后端 `display` 内建一致）。 */
export function displayOp(args: QyValue[], env: QyValue): QyValue {
  const values = args.map((arg) => resolveLiteral(arg, env));
  writer(values.map(formatValue).join(' '));
  return values.length === 0 ? null : values[values.length - 1];
}

/** `newline`：只输出换行。 */
export function newlineOp(_args: QyValue[], _env: QyValue): QyValue {
  writer('\n');
  return QY_NIL;
}

export function ioBindings(): Record<string, QyValue> {
  return {
    print: printOp,
    echo: printOp,
    display: displayOp,
    newline: newlineOp,
  };
}
