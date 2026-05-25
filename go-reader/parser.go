package reader

import "fmt"

// SyntaxError is the reader's error type.
type SyntaxError struct {
	Message string
	Span    *SourceSpan
}

func (e *SyntaxError) Error() string {
	if e.Span != nil {
		return fmt.Sprintf("%s at %s", e.Message, e.Span.Format())
	}
	return e.Message
}

// parser turns a token stream into Forms.
type parser struct {
	tokens     []token
	pos        int
	sourceName string
}

func newParser(tokens []token, sourceName string) *parser {
	return &parser{tokens: tokens, pos: 0, sourceName: sourceName}
}

func (p *parser) peek() token {
	if p.pos >= len(p.tokens) {
		return token{typ: tokEOF}
	}
	return p.tokens[p.pos]
}

func (p *parser) advance() token {
	tok := p.peek()
	if tok.typ != tokEOF {
		p.pos++
	}
	return tok
}

func (p *parser) tokenSpan(tok token) *SourceSpan {
	return &SourceSpan{
		Source:      p.sourceName,
		StartLine:   tok.line,
		StartColumn: tok.column,
		EndLine:     tok.endLine,
		EndColumn:   tok.endColumn,
	}
}

func (p *parser) parseProgram() ([]Form, error) {
	var forms []Form
	for p.peek().typ != tokEOF {
		form, err := p.parseForm()
		if err != nil {
			return nil, err
		}
		forms = append(forms, form)
	}
	return forms, nil
}

func (p *parser) parseForm() (Form, error) {
	tok := p.peek()
	switch tok.typ {
	case tokLParen:
		return p.parseList()
	case tokBareSymbol, tokQuotedSymbol, tokRawQuotedSymbol, tokMultilineSymbol, tokRawMultilineSymbol:
		p.advance()
		return Symbol{Name: tok.value, Span: p.tokenSpan(tok)}, nil
	case tokTaggedQuotedSymbol, tokTaggedMultilineSymbol:
		p.advance()
		return p.expandTaggedLiteral(tok), nil
	case tokDot:
		p.advance()
		return Symbol{Name: ".", Span: p.tokenSpan(tok)}, nil
	case tokRParen:
		return nil, &SyntaxError{
			Message: "unexpected ')'",
			Span:    p.tokenSpan(tok),
		}
	case tokEOF:
		return nil, &SyntaxError{
			Message: "unexpected end of input",
			Span:    &SourceSpan{Source: p.sourceName},
		}
	default:
		return nil, &SyntaxError{
			Message: fmt.Sprintf("unexpected token %q", tok.value),
			Span:    p.tokenSpan(tok),
		}
	}
}

func (p *parser) parseList() (Form, error) {
	open := p.advance() // consume '('
	span := p.tokenSpan(open)

	var items []Form
	dotIndex := -1

	for {
		tok := p.peek()
		if tok.typ == tokRParen {
			close := p.advance()
			span.EndLine = close.endLine
			span.EndColumn = close.endColumn
			break
		}
		if tok.typ == tokEOF {
			return nil, &SyntaxError{
				Message: "unclosed parenthesis",
				Span:    span,
			}
		}
		if tok.typ == tokDot {
			p.advance()
			dotIndex = len(items)
			items = append(items, nil) // placeholder for dot
			continue
		}
		form, err := p.parseForm()
		if err != nil {
			return nil, err
		}
		items = append(items, form)
	}

	if dotIndex == -1 {
		// Proper list
		return ListToChain(items, span), nil
	}

	// Dotted pair: validate
	if dotIndex == 0 {
		return nil, &SyntaxError{
			Message: "dotted pair must have a head before .",
			Span:    span,
		}
	}
	if dotIndex != len(items)-2 {
		return nil, &SyntaxError{
			Message: "dotted pair must have exactly one tail after .",
			Span:    span,
		}
	}

	heads := make([]Form, 0, dotIndex)
	for i := 0; i < dotIndex; i++ {
		heads = append(heads, items[i])
	}
	tail := items[dotIndex+1]

	// Build improper list
	var result Form = tail
	for i := len(heads) - 1; i >= 0; i-- {
		result = Cons(heads[i], result, span)
	}
	return result, nil
}

func (p *parser) expandTaggedLiteral(tok token) Form {
	span := p.tokenSpan(tok)
	tag, literal := splitTaggedLiteral(tok.value)

	quoteForm := ListToChain([]Form{
		Symbol{Name: "quote", Span: span},
		Symbol{Name: literal, Span: span},
	}, span)
	return ListToChain([]Form{
		Symbol{Name: tag, Span: span},
		quoteForm,
	}, span)
}

// ReadRaw parses source into raw forms without surface dialect expansion.
func ReadRaw(source string, sourceName string) ([]Form, error) {
	tokens, err := tokenize(source, sourceName)
	if err != nil {
		return nil, err
	}
	p := newParser(tokens, sourceName)
	return p.parseProgram()
}

// Read parses source and applies surface dialect expansion.
func Read(source string, sourceName string) ([]Form, error) {
	forms, err := ReadRaw(source, sourceName)
	if err != nil {
		return nil, err
	}
	return ExpandSurfaceDialect(forms), nil
}

// ReadOne parses exactly one form from source.
func ReadOne(source string, sourceName string) (Form, error) {
	forms, err := Read(source, sourceName)
	if err != nil {
		return nil, err
	}
	if len(forms) != 1 {
		return nil, &SyntaxError{
			Message: fmt.Sprintf("expected exactly one form, got %d", len(forms)),
		}
	}
	return forms[0], nil
}
