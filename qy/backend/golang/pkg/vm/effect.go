package vm

import "fmt"

type EffectSignal struct {
	Effect       string
	Arg          Value
	Continuation *Continuation
	Resumable    bool
}

func (e *EffectSignal) Error() string {
	return fmt.Sprintf("effect signal: %s", e.Effect)
}
