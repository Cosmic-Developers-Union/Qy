// stdlib 共享支撑：effect 触发与 identity continuation。
//
// 对应 `qy/session/number_ops.py::_perform_effect` 与
// `qy/vm/instance/machine.py::_make_identity_continuation`。

import { QyEffectSignal } from '../errors.ts';
import {
  Continuation,
  DictValue,
  FloatValue,
  IntValue,
  QY_NIL,
  QY_T,
  StringValue,
  Symbol,
  type QyValue,
} from '../values.ts';

/** 恒等 continuation（对应 `_make_identity_continuation`）。 */
export function identityContinuation(effect: string, resumable: boolean): Continuation {
  return new Continuation(effect, resumable, (value: QyValue) => value);
}

/**
 * 触发一个 effect。
 *
 * 与 Python 一致：`resumable=False` 时 continuation 不可恢复，
 * VM 只会把它交给 handler 或继续向上抛。
 */
export function performEffect(name: string, payload: QyValue, resumable = false): never {
  throw new QyEffectSignal(name, toEffectPayload(payload), identityContinuation(name, resumable), resumable);
}

/** 把宿主 level 的 effect 载荷转换为 Qy `DictValue`（symbol 键 + Qy 值）。 */
function toEffectPayload(payload: QyValue): QyValue {
  if (payload === null || typeof payload !== 'object' || Array.isArray(payload)) return payload;
  const proto = Object.getPrototypeOf(payload);
  if (proto !== Object.prototype && proto !== null) return payload;
  const entries: [QyValue, QyValue][] = [];
  for (const [key, value] of Object.entries(payload as Record<string, unknown>)) {
    entries.push([new Symbol(key), toPayloadValue(value)]);
  }
  return new DictValue(entries);
}

function toPayloadValue(value: unknown): QyValue {
  if (typeof value === 'string') return new StringValue(value);
  if (typeof value === 'bigint') return new IntValue(value);
  if (typeof value === 'number') {
    return Number.isInteger(value) ? new IntValue(BigInt(value)) : new FloatValue(value);
  }
  if (typeof value === 'boolean') return value ? QY_T : QY_NIL;
  return value as QyValue;
}
