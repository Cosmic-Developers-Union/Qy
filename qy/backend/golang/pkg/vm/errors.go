package vm

import "fmt"

// Qy VM 错误类型。
//
// 对应 Python `qy/errors/__init__.py` 的类层次：
//
//	QyError
//	  └ EvaluationError
//	      ├ QyResolveError
//	      ├ QyTypeError / QyArityError / QyReifyError
//	      └ QyEffectSignal（经由 QyEffectError）
//
// 这个层次在 VM 里有实际语义：`call` 只把「非 Qy 错误」包装成 RuntimeError，
// effect signal 必须原样向上传播（HANDLE / CALL 的 handler 分派靠它）。

// EvaluationError 是求值期错误基类（对应 Python `EvaluationError`）。
type EvaluationError struct {
	Message string
}

func (e *EvaluationError) Error() string { return e.Message }

// ResolveError 表示符号无法解析。
type ResolveError struct {
	EvaluationError
}

// NewResolveError 构造符号解析错误。
func NewResolveError(message string) *ResolveError {
	return &ResolveError{EvaluationError: EvaluationError{Message: message}}
}

// TypeError 表示类型错误。
type TypeError struct {
	EvaluationError
}

// NewTypeError 构造类型错误。
func NewTypeError(message string) *TypeError {
	return &TypeError{EvaluationError: EvaluationError{Message: message}}
}

// ArityError 表示元数错误。
type ArityError struct {
	EvaluationError
}

// NewArityError 构造元数错误。
func NewArityError(message string) *ArityError {
	return &ArityError{EvaluationError: EvaluationError{Message: message}}
}

// ReifyError 表示 reify 失败。
type ReifyError struct {
	EvaluationError
}

// NewReifyError 构造 reify 错误。
func NewReifyError(message string) *ReifyError {
	return &ReifyError{EvaluationError: EvaluationError{Message: message}}
}

// AggregateError 聚合多个并行分支的错误（对应 Python `QyAggregateError`）。
type AggregateError struct {
	EvaluationError
	Errors []error
}

// NewAggregateError 构造聚合错误。
func NewAggregateError(message string, errors []error) *AggregateError {
	return &AggregateError{EvaluationError: EvaluationError{Message: message}, Errors: errors}
}

// EffectError 是代数效应错误基类（对应 Python `QyEffectError`）。
type EffectError struct {
	EvaluationError
}

// NewEffectError 构造效应错误。
func NewEffectError(message string) *EffectError {
	return &EffectError{EvaluationError: EvaluationError{Message: message}}
}

// RuntimeError 是通用运行时错误。
type RuntimeError struct {
	EvaluationError
}

// NewRuntimeError 构造通用运行时错误。
func NewRuntimeError(message string) *RuntimeError {
	return &RuntimeError{EvaluationError: EvaluationError{Message: message}}
}

// EffectSignal 是代数效应信号（对应 Python `QyEffectSignal`）。
//
// Python VM 用异常传播 effect 的 "unwind"；HANDLE / CALL 的 handler 分派
// 就是在 catch 中完成的。Go 侧同理：它实现 error，由调用方按类型断言捕获。
type EffectSignal struct {
	Effect       string
	Arg          Value
	Continuation *Continuation
	Resumable    bool
}

func (e *EffectSignal) Error() string { return "effect: " + e.Effect }

// asEffectSignal 从 error 中提取 effect 信号。
func asEffectSignal(err error) (*EffectSignal, bool) {
	signal, ok := err.(*EffectSignal)
	return signal, ok
}

// IdentityContinuation 构造恒等 continuation
// （对应 `machine.py::_make_identity_continuation`）。
func IdentityContinuation(effect string, resumable bool) *Continuation {
	return &Continuation{
		Effect:    effect,
		Resumable: resumable,
		ResumeFn:  func(value Value) (Value, error) { return value, nil },
	}
}

// PerformEffect 触发一个 effect（对应 `qy/session/number_ops.py::_perform_effect`）。
//
// resumable=False 时 continuation 不可恢复：VM 只会把它交给 handler 或继续向上抛。
func PerformEffect(name string, payload Value, resumable bool) error {
	return &EffectSignal{
		Effect:       name,
		Arg:          payload,
		Continuation: IdentityContinuation(name, resumable),
		Resumable:    resumable,
	}
}

// UnhandledEffectError 表示 effect 一路冒泡到程序顶层。
type UnhandledEffectError struct {
	Effect string
	Arg    Value
}

func (e *UnhandledEffectError) Error() string {
	return fmt.Sprintf("unhandled effect: %s (arg: %v)", e.Effect, e.Arg)
}
