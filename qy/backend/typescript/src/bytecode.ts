// 字节码 JSON 交换格式的装载器。
//
// 契约真源：`qy/backend/vm/bytecode.py` 的 `serialize_bytecode_json`（编码）与
// `load_bytecode_json`（解码）。本文件是解码侧的 TypeScript 实现，语义逐条对齐
// `load_bytecode_json`：
//
//   - 操作数先按 `reg` 还原为数字，其余走 decodeValue；
//   - `{type, class, value}` 载荷是 Qy 语义值（`qy/sem/core.py` 的值类），
//     按 class 名重建对应值；没有 `class` 的裸标量保持宿主标量语义；
//   - handler_specs → [Symbol, number][]；import_specs → {name, alias}[]；
//     reg_tuple/symbol_tuple → 数组；chain → Chain。

import { QyError } from './errors.ts';
import {
  ArrayValue,
  Chain,
  CharValue,
  ComplexValue,
  DictValue,
  EffectDefinition,
  Float16Value,
  Float128Value,
  Float32Value,
  FloatValue,
  HashMapValue,
  Int8Value,
  Int16Value,
  Int32Value,
  Int64Value,
  IntValue,
  ListValue,
  NumberValue,
  QY_NIL,
  QY_NONE,
  QY_T,
  RationalValue,
  SetValue,
  StringValue,
  Symbol,
  TupleValue,
  UInt8Value,
  UInt16Value,
  UInt32Value,
  UInt64Value,
  type QyValue,
} from './values.ts';

/** 一条指令。operands 已按契约解码。 */
export interface Instruction {
  opcode: string;
  operands: QyValue[];
}

/** 一个字节码函数。 */
export interface BytecodeFunction {
  name: string;
  params: string[];
  registerCount: number;
  instructions: Instruction[];
}

/** 一个字节码程序。 */
export interface BytecodeProgram {
  version: number;
  main: number;
  functions: BytecodeFunction[];
  /** 卫生宏别名 → 原始符号名。见 report：这是交换格式里唯一能恢复宏卫生的字段。 */
  hygieneBindings: Map<string, string>;
}

/** handler 规格：effect 名 + handler 函数下标。 */
export type HandlerSpec = [Symbol, number];

/** import 规格：原名 + 别名。 */
export interface ImportSpec {
  name: string;
  alias: string;
}

const SEMANTIC_CLASSES: Record<string, new (...args: never[]) => unknown> = {
  IntValue: IntValue as unknown as new (...args: never[]) => unknown,
  Int8Value: Int8Value as unknown as new (...args: never[]) => unknown,
  Int16Value: Int16Value as unknown as new (...args: never[]) => unknown,
  Int32Value: Int32Value as unknown as new (...args: never[]) => unknown,
  Int64Value: Int64Value as unknown as new (...args: never[]) => unknown,
  UInt8Value: UInt8Value as unknown as new (...args: never[]) => unknown,
  UInt16Value: UInt16Value as unknown as new (...args: never[]) => unknown,
  UInt32Value: UInt32Value as unknown as new (...args: never[]) => unknown,
  UInt64Value: UInt64Value as unknown as new (...args: never[]) => unknown,
  FloatValue: FloatValue as unknown as new (...args: never[]) => unknown,
  Float16Value: Float16Value as unknown as new (...args: never[]) => unknown,
  Float32Value: Float32Value as unknown as new (...args: never[]) => unknown,
  Float128Value: Float128Value as unknown as new (...args: never[]) => unknown,
};

function asInt(value: unknown, fallback = 0): number {
  if (typeof value === 'boolean') return value ? 1 : 0;
  if (typeof value === 'number') return Math.trunc(value);
  if (typeof value === 'string') {
    const parsed = Number.parseInt(value, 10);
    return Number.isNaN(parsed) ? fallback : parsed;
  }
  return fallback;
}

/** 把 `{type, class, value}` 还原为 Qy 语义值；不是语义值返回 undefined。 */
function decodeSemanticValue(payload: Record<string, unknown>): QyValue | undefined {
  const className = payload['class'];
  if (typeof className !== 'string') return undefined;
  const raw = payload['value'];
  const data: Record<string, unknown> = raw && typeof raw === 'object' ? (raw as Record<string, unknown>) : {};
  const field = (name: string): QyValue => decodeValue(data[name]);

  switch (className) {
    case 'IntValue':
    case 'Int8Value':
    case 'Int16Value':
    case 'Int32Value':
    case 'Int64Value':
    case 'UInt8Value':
    case 'UInt16Value':
    case 'UInt32Value':
    case 'UInt64Value':
    case 'FloatValue':
    case 'Float16Value':
    case 'Float32Value':
    case 'Float128Value': {
      const ctor = SEMANTIC_CLASSES[className];
      return new (ctor as unknown as new (v: number) => NumberValue)(Number(field('value')));
    }
    case 'StringValue':
      return new StringValue(String(field('value')));
    case 'CharValue':
      return new CharValue(String(field('value')));
    case 'TupleValue':
      return new TupleValue(toArray(field('items')));
    case 'ListValue':
      return new ListValue(toArray(field('items')));
    case 'SetValue':
      return new SetValue(toArray(field('items')));
    case 'DictValue':
      return new DictValue(toEntries(field('entries')));
    case 'HashMapValue':
      return new HashMapValue(toEntries(field('entries')));
    case 'ArrayValue':
      return new ArrayValue(String(field('element_type') ?? ''), toArray(field('items')));
    case 'ComplexValue':
      return new ComplexValue(field('real') as NumberValue, field('imag') as NumberValue);
    case 'RationalValue':
      return new RationalValue(field('numerator') as NumberValue, field('denominator') as NumberValue);
    default:
      return undefined;
  }
}

function toArray(value: QyValue): QyValue[] {
  return Array.isArray(value) ? value : [];
}

function toEntries(value: QyValue): [QyValue, QyValue][] {
  if (!Array.isArray(value)) return [];
  return value.map((item) => (Array.isArray(item) && item.length === 2 ? [item[0], item[1]] : [item, QY_NIL]));
}

/** 解码 chain 载荷（`{head, tail}` 递归，null 结尾表示 nil）。 */
function decodeChain(payload: unknown): QyValue {
  if (payload === null || payload === undefined) return QY_NIL;
  if (typeof payload !== 'object') return decodeValue(payload);
  const node = payload as Record<string, unknown>;
  const tail = decodeChain(node['tail']);
  return new Chain(decodeValue(node['head']), tail);
}

/** 解码任意值的标准路径（对应 `load_bytecode_json.decode_value`）。 */
export function decodeValue(payload: unknown): QyValue {
  if (payload === null || typeof payload !== 'object') return payload;
  const record = payload as Record<string, unknown>;
  const semantic = decodeSemanticValue(record);
  if (semantic !== undefined) return semantic;
  const kind = record['type'];
  const raw = record['value'];
  switch (kind) {
    case 'nil':
      return QY_NIL;
    case 't':
      return QY_T;
    case 'none':
      return QY_NONE;
    case 'int':
    case 'float':
    case 'bool':
    case 'string':
      return raw;
    case 'symbol':
      return new Symbol(String(raw));
    case 'chain':
      return decodeChain(raw);
    case 'effect_def': {
      const data = raw && typeof raw === 'object' ? (raw as Record<string, unknown>) : {};
      return new EffectDefinition(String(data['name'] ?? ''), Boolean(data['resumable'] ?? true));
    }
    case 'list':
      return Array.isArray(raw) ? raw.map(decodeValue) : [];
    case 'tuple':
      return Array.isArray(raw) ? raw.map(decodeValue) : [];
    case 'reg_tuple':
      return Array.isArray(raw) ? raw.map((item) => asInt(item)) : [];
    case 'symbol_tuple':
      return Array.isArray(raw) ? raw.map((item) => new Symbol(String(item))) : [];
    case 'handler_specs': {
      const specs = Array.isArray(raw) ? raw : [];
      return specs
        .filter((spec): spec is Record<string, unknown> => Boolean(spec) && typeof spec === 'object')
        .map((spec) => [new Symbol(String(spec['effect'] ?? '')), asInt(spec['handler_fn'], -1)] as HandlerSpec);
    }
    case 'import_specs': {
      const specs = Array.isArray(raw) ? raw : [];
      return specs
        .filter((spec): spec is Record<string, unknown> => Boolean(spec) && typeof spec === 'object')
        .map((spec) => ({ name: String(spec['name'] ?? ''), alias: String(spec['alias'] ?? '') }) as ImportSpec);
    }
    case 'unknown':
      throw new QyError(
        `bytecode JSON contains an unencodable value: ${String(raw)}; ` +
          'the interchange format must encode every constant',
      );
    default:
      return raw;
  }
}

/** 解码单个操作数：`reg` → number，其余走 decodeValue。 */
export function decodeOperand(payload: unknown): QyValue {
  if (payload && typeof payload === 'object') {
    const record = payload as Record<string, unknown>;
    if (record['type'] === 'reg') {
      const raw = record['value'];
      return typeof raw === 'number' || typeof raw === 'boolean' ? asInt(raw) : raw;
    }
  }
  return decodeValue(payload);
}

/**
 * 从 `qy export` 的 JSON 文本装载程序。
 *
 * 注意 `hygieneBindings`：Python 的 `load_bytecode_json` 会丢弃它（`BytecodeProgram`
 * 没有对应字段），导致带卫生宏的产物无法被执行。这里保留它，见最终报告。
 */
export function loadBytecodeJson(text: string): BytecodeProgram {
  const data = JSON.parse(text) as Record<string, unknown>;
  const version = data['version'];
  if (version !== 1) {
    throw new QyError(`unsupported bytecode JSON version: ${String(version)}`);
  }
  const rawFunctions = Array.isArray(data['functions']) ? data['functions'] : [];
  const functions: BytecodeFunction[] = rawFunctions.map((rawFunction: unknown) => {
    const fn = (rawFunction ?? {}) as Record<string, unknown>;
    const rawInstructions = Array.isArray(fn['instructions']) ? fn['instructions'] : [];
    const instructions: Instruction[] = rawInstructions.map((rawInstruction: unknown) => {
      const inst = (rawInstruction ?? {}) as Record<string, unknown>;
      const rawOperands = Array.isArray(inst['operands']) ? inst['operands'] : [];
      return {
        opcode: String(inst['opcode'] ?? ''),
        operands: rawOperands.map(decodeOperand),
      };
    });
    const rawParams = Array.isArray(fn['params']) ? fn['params'] : [];
    return {
      name: String(fn['name'] ?? ''),
      params: rawParams.map((param) => String(param)),
      registerCount: asInt(fn['register_count'], 0),
      instructions,
    };
  });
  const hygieneBindings = new Map<string, string>();
  const rawHygiene = data['hygiene_bindings'];
  if (rawHygiene && typeof rawHygiene === 'object') {
    for (const [key, value] of Object.entries(rawHygiene as Record<string, unknown>)) {
      hygieneBindings.set(key, String(value));
    }
  }
  return {
    version: 1,
    main: asInt(data['main'], 0),
    functions,
    hygieneBindings,
  };
}
