// stdlib 共享支撑：effect 触发与 identity continuation。
//
// 对应 `qy/session/number_ops.py::_perform_effect` 与
// `qy/vm/instance/machine.py::_make_identity_continuation`。

import { QyEffectSignal } from '../errors.ts';
import { Continuation, type QyValue } from '../values.ts';

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
  throw new QyEffectSignal(name, payload, identityContinuation(name, resumable), resumable);
}
