package vm

import (
	"strings"
)

type SymbolSpace struct {
	name     string
	bindings map[string]Value
	parent   *SymbolSpace
}

func NewSymbolSpace(name string, parent *SymbolSpace) *SymbolSpace {
	return &SymbolSpace{
		name:     name,
		bindings: make(map[string]Value),
		parent:   parent,
	}
}

func (ss *SymbolSpace) Resolve(name string) (Value, bool) {
	current := ss
	for current != nil {
		if v, ok := current.bindings[name]; ok {
			return v, true
		}
		current = current.parent
	}
	base := deHygiene(name)
	if base != name {
		current = ss
		for current != nil {
			if v, ok := current.bindings[base]; ok {
				return v, true
			}
			current = current.parent
		}
	}
	return nil, false
}

func (ss *SymbolSpace) Define(name string, value Value) {
	ss.bindings[name] = value
}

func (ss *SymbolSpace) DefineOnce(name string, value Value) error {
	if _, exists := ss.bindings[name]; exists {
		return nil
	}
	ss.bindings[name] = value
	return nil
}

func (ss *SymbolSpace) Child() *SymbolSpace {
	return NewSymbolSpace("", ss)
}

func (ss *SymbolSpace) Bindings() map[string]Value {
	return ss.bindings
}

func deHygiene(name string) string {
	if !strings.HasPrefix(name, "__qy_hygiene_def_") {
		return name
	}
	rest := strings.TrimPrefix(name, "__qy_hygiene_def_")
	lastUnderscore := strings.LastIndex(rest, "_")
	if lastUnderscore < 0 {
		return rest
	}
	suffix := rest[lastUnderscore+1:]
	isDigits := true
	for _, c := range suffix {
		if c < '0' || c > '9' {
			isDigits = false
			break
		}
	}
	if isDigits && lastUnderscore > 0 {
		return rest[:lastUnderscore]
	}
	if isDigits && lastUnderscore == 0 {
		return rest[:lastUnderscore]
	}
	return rest
}
