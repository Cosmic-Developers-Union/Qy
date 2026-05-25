package reader

import "fmt"

// SourceSpan tracks the location of a form in source text.
type SourceSpan struct {
	Source      string
	StartLine   int
	StartColumn int
	EndLine     int
	EndColumn   int
}

func (s *SourceSpan) Format() string {
	loc := s.Source
	if loc == "" {
		loc = "<source>"
	}
	if s.StartLine == 0 && s.StartColumn == 0 {
		return loc
	}
	return fmt.Sprintf("%s:%d:%d", loc, s.StartLine, s.StartColumn)
}

// Symbol is an atom with a name and optional source span.
// All atoms (numbers, strings, keywords, identifiers) are symbols at the reader level.
type Symbol struct {
	Name string
	Span *SourceSpan
}

func (s Symbol) Equal(other Form) bool {
	o, ok := other.(Symbol)
	if !ok {
		return false
	}
	return s.Name == o.Name
}

func (s Symbol) GetSpan() *SourceSpan { return s.Span }
func (s Symbol) formNode()            {}
func (s Symbol) String() string       { return s.Name }

// Chain is an immutable cons cell.
type Chain struct {
	Head Form
	Tail Form
	Span *SourceSpan
}

func (c *Chain) Equal(other Form) bool {
	o, ok := other.(*Chain)
	if !ok {
		return false
	}
	if !c.Head.Equal(o.Head) {
		return false
	}
	return c.Tail.Equal(o.Tail)
}

func (c *Chain) GetSpan() *SourceSpan { return c.Span }
func (c *Chain) formNode()            {}

func (c *Chain) Len() int {
	count := 0
	var current Form = c
	for IsChain(current) {
		count++
		current = Cdr(current)
	}
	if !IsNil(current) {
		return -1
	}
	return count
}

func (c *Chain) ToSlice() []Form {
	var items []Form
	var current Form = c
	for IsChain(current) {
		items = append(items, Car(current))
		current = Cdr(current)
	}
	return items
}

// Nil represents the empty chain.
type Nil struct{}

func (n Nil) Equal(other Form) bool {
	_, ok := other.(Nil)
	return ok
}

func (n Nil) GetSpan() *SourceSpan { return nil }
func (n Nil) formNode()            {}
func (n Nil) String() string       { return "()" }

// QyNil is the singleton nil value.
var QyNil Form = Nil{}

// Form is the union type for all reader output.
type Form interface {
	formNode()
	Equal(other Form) bool
	GetSpan() *SourceSpan
}

// Cons constructs a new cons cell.
func Cons(head, tail Form, span *SourceSpan) *Chain {
	return &Chain{Head: head, Tail: tail, Span: span}
}

// Car returns the head of a chain.
func Car(form Form) Form {
	c, ok := form.(*Chain)
	if !ok {
		panic(fmt.Sprintf("car expects a Chain, got %T", form))
	}
	return c.Head
}

// Cdr returns the tail of a chain.
func Cdr(form Form) Form {
	c, ok := form.(*Chain)
	if !ok {
		panic(fmt.Sprintf("cdr expects a Chain, got %T", form))
	}
	return c.Tail
}

// IsNil checks if a form is nil.
func IsNil(form Form) bool {
	_, ok := form.(Nil)
	return ok
}

// IsChain checks if a form is a Chain.
func IsChain(form Form) bool {
	_, ok := form.(*Chain)
	return ok
}

// ListToChain builds a proper chain from a slice of forms.
func ListToChain(items []Form, span *SourceSpan) Form {
	return ListToChainWithTail(items, QyNil, span)
}

// ListToChainWithTail builds a chain from items with a given tail.
func ListToChainWithTail(items []Form, tail Form, span *SourceSpan) Form {
	result := tail
	for i := len(items) - 1; i >= 0; i-- {
		var s *SourceSpan
		if i == 0 {
			s = span
		}
		result = Cons(items[i], result, s)
	}
	return result
}

// ChainToSlice converts a proper chain to a slice. Returns (items, tail).
func ChainToSlice(chain Form) ([]Form, Form) {
	var items []Form
	current := chain
	for IsChain(current) {
		items = append(items, Car(current))
		current = Cdr(current)
	}
	return items, current
}

// GetSpan extracts the SourceSpan from a form.
func GetSpan(form Form) *SourceSpan {
	if form == nil {
		return nil
	}
	return form.GetSpan()
}

// Sym is a convenience constructor for Symbol (no span).
func Sym(name string) Symbol {
	return Symbol{Name: name}
}

// L is a convenience constructor for a proper chain (no span).
func L(items ...Form) Form {
	return ListToChain(items, nil)
}
