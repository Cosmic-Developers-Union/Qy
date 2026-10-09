// Qy VM 错误类型。
//
// 对应 Python 侧 `qy/errors/__init__.py` 的类层次：
//   QyError
//     └ EvaluationError
//         ├ QyResolveError
//         ├ QyTypeError / QyArityError / QyReifyError
//         └ QyEffectSignal（经由 QyEffectError）
//
// 这个层次在 VM 里有实际语义：`_call` 只把「非 Qy 错误」包装成
// QyRuntimeError，effect signal 必须原样向上传播。因此这里保留一个
// `EvaluationError` 基类。

/** 所有 Qy 错误/信号的基类。 */
export class QyError extends Error {
  constructor(message: string) {
    super(message);
    this.name = new.target.name;
  }
}

/** 求值期错误基类（对应 Python `EvaluationError`）。 */
export class EvaluationError extends QyError {}

/** 符号无法解析。 */
export class QyResolveError extends EvaluationError {}

/** 类型错误。 */
export class QyTypeError extends EvaluationError {}

/** 元数错误。 */
export class QyArityError extends EvaluationError {}

/** reify 失败。 */
export class QyReifyError extends EvaluationError {}

/** 通用运行时错误。 */
export class QyRuntimeError extends EvaluationError {}

/**
 * `parallel` 的聚合错误（对应 Python `qy.errors.QyAggregateError`）。
 * Python `_parallel_gather(aggregate_errors=True)` 收集全部 thunk 错误后抛出它。
 */
export class QyAggregateError extends EvaluationError {
  constructor(
    message: string,
    readonly errors: unknown[],
  ) {
    super(message);
  }
}

/**
 * 代数效应信号（对应 Python `QyEffectSignal`）。
 *
 * 它是 `EvaluationError` 的子类，Python VM 用异常来传播 effect 的
 * "unwind"；HANDLE / CALL 的 handler 分派就是在 catch 中完成的。
 */
/** 代数效应错误基类（对应 Python `QyEffectError`）。 */
export class QyEffectError extends EvaluationError {}

export class QyEffectSignal extends QyEffectError {
  constructor(
    readonly effect: string,
    readonly arg: unknown,
    public continuation: ContinuationLike,
    readonly resumable: boolean,
  ) {
    super(`unhandled effect '${effect}'`);
  }
}

/** continuation 的最小结构（避免 errors.ts 依赖 values.ts 造成循环导入）。 */
export interface ContinuationLike {
  readonly effect: string;
  readonly resumable: boolean;
  resume(value: unknown): unknown;
}
