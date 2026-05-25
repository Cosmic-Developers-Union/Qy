package reader

import (
	"fmt"
	"strings"
	"unicode"
	"unicode/utf8"
)

type tokenType int

const (
	tokLParen tokenType = iota
	tokRParen
	tokDot
	tokBareSymbol
	tokQuotedSymbol
	tokRawQuotedSymbol
	tokTaggedQuotedSymbol
	tokMultilineSymbol
	tokRawMultilineSymbol
	tokTaggedMultilineSymbol
	tokEOF
)

type token struct {
	typ       tokenType
	value     string
	line      int
	column    int
	endLine   int
	endColumn int
}

type lexer struct {
	source     string
	sourceName string
	pos        int
	line       int
	column     int
}

func newLexer(source, sourceName string) *lexer {
	return &lexer{
		source:     source,
		sourceName: sourceName,
		pos:        0,
		line:       1,
		column:     1,
	}
}

func (l *lexer) peek() rune {
	if l.pos >= len(l.source) {
		return 0
	}
	r, _ := utf8.DecodeRuneInString(l.source[l.pos:])
	return r
}

func (l *lexer) advance() rune {
	if l.pos >= len(l.source) {
		return 0
	}
	r, size := utf8.DecodeRuneInString(l.source[l.pos:])
	l.pos += size
	if r == '\n' {
		l.line++
		l.column = 1
	} else {
		l.column++
	}
	return r
}

func (l *lexer) skipWhitespaceAndComments() {
	for l.pos < len(l.source) {
		r := l.peek()
		if unicode.IsSpace(r) {
			l.advance()
		} else if r == ';' {
			for l.pos < len(l.source) && l.peek() != '\n' {
				l.advance()
			}
		} else {
			break
		}
	}
}

func (l *lexer) nextToken() (token, error) {
	l.skipWhitespaceAndComments()

	if l.pos >= len(l.source) {
		return token{typ: tokEOF, line: l.line, column: l.column}, nil
	}

	startLine := l.line
	startCol := l.column
	startPos := l.pos
	r := l.peek()

	switch {
	case r == '(':
		l.advance()
		return token{typ: tokLParen, value: "(", line: startLine, column: startCol, endLine: l.line, endColumn: l.column}, nil
	case r == ')':
		l.advance()
		return token{typ: tokRParen, value: ")", line: startLine, column: startCol, endLine: l.line, endColumn: l.column}, nil
	case r == '"':
		return l.lexQuotedOrMultiline(startLine, startCol, startPos, "")
	case r == 'r' || r == 'R':
		nextPos := l.pos + 1
		if nextPos < len(l.source) && l.source[nextPos] == '"' {
			return l.lexRawQuoted(startLine, startCol, startPos)
		}
		return l.lexBareOrTagged(startLine, startCol, startPos)
	default:
		return l.lexBareOrTagged(startLine, startCol, startPos)
	}
}

func (l *lexer) lexQuotedOrMultiline(startLine, startCol, startPos int, prefix string) (token, error) {
	if l.pos+2 < len(l.source) && l.source[l.pos:l.pos+3] == `"""` {
		return l.lexMultiline(startLine, startCol, startPos, prefix)
	}
	return l.lexQuotedSymbol(startLine, startCol, startPos, prefix)
}

func (l *lexer) lexMultiline(startLine, startCol, startPos int, prefix string) (token, error) {
	// skip opening """
	l.advance() // "
	l.advance() // "
	l.advance() // "

	for {
		if l.pos >= len(l.source) {
			return token{}, &SyntaxError{
				Message: "unterminated multiline string",
				Span:    &SourceSpan{Source: l.sourceName, StartLine: startLine, StartColumn: startCol, EndLine: l.line, EndColumn: l.column},
			}
		}
		if l.pos+2 < len(l.source) && l.source[l.pos:l.pos+3] == `"""` {
			l.advance()
			l.advance()
			l.advance()
			value := l.source[startPos:l.pos]
			typ := tokMultilineSymbol
			if prefix == "r" || prefix == "R" {
				typ = tokRawMultilineSymbol
			} else if prefix != "" {
				typ = tokTaggedMultilineSymbol
			}
			return token{typ: typ, value: value, line: startLine, column: startCol, endLine: l.line, endColumn: l.column}, nil
		}
		l.advance()
	}
}

func (l *lexer) lexQuotedSymbol(startLine, startCol, startPos int, prefix string) (token, error) {
	l.advance() // opening "

	for {
		if l.pos >= len(l.source) {
			return token{}, &SyntaxError{
				Message: "unterminated string",
				Span:    &SourceSpan{Source: l.sourceName, StartLine: startLine, StartColumn: startCol, EndLine: l.line, EndColumn: l.column},
			}
		}
		r := l.peek()
		if r == '\\' {
			l.advance()
			if l.pos < len(l.source) {
				l.advance()
			}
		} else if r == '"' {
			l.advance()
			value := l.source[startPos:l.pos]
			typ := tokQuotedSymbol
			if prefix == "r" || prefix == "R" {
				typ = tokRawQuotedSymbol
			} else if prefix != "" {
				typ = tokTaggedQuotedSymbol
			}
			return token{typ: typ, value: value, line: startLine, column: startCol, endLine: l.line, endColumn: l.column}, nil
		} else {
			l.advance()
		}
	}
}

func (l *lexer) lexRawQuoted(startLine, startCol, startPos int) (token, error) {
	prefix := string(l.peek())
	l.advance() // r or R
	return l.lexQuotedOrMultiline(startLine, startCol, startPos, prefix)
}

func (l *lexer) lexBareOrTagged(startLine, startCol, startPos int) (token, error) {
	// Read the bare symbol characters, watching for a quote that would make it tagged
	for l.pos < len(l.source) {
		r := l.peek()
		if r == '"' {
			// This could be a tagged quoted or tagged multiline symbol
			prefix := l.source[startPos:l.pos]
			if isValidTagPrefix(prefix) {
				return l.lexQuotedOrMultiline(startLine, startCol, startPos, prefix)
			}
			break
		}
		if isBareTerminator(r) {
			break
		}
		l.advance()
	}

	value := l.source[startPos:l.pos]
	if value == "" {
		return token{}, &SyntaxError{
			Message: fmt.Sprintf("unexpected character %q", l.peek()),
			Span:    &SourceSpan{Source: l.sourceName, StartLine: startLine, StartColumn: startCol, EndLine: l.line, EndColumn: l.column},
		}
	}

	typ := tokBareSymbol
	if value == "." {
		typ = tokDot
	}
	return token{typ: typ, value: value, line: startLine, column: startCol, endLine: l.line, endColumn: l.column}, nil
}

func isBareTerminator(r rune) bool {
	return r == '(' || r == ')' || unicode.IsSpace(r) || r == '"' || r == ';'
}

func isValidTagPrefix(s string) bool {
	if s == "" {
		return false
	}
	for _, r := range s {
		if r == '(' || r == ')' || unicode.IsSpace(r) || r == '"' || r == '\'' || r == ';' || r == '`' || r == ',' || r == '@' {
			return false
		}
	}
	return true
}

// Tokenize returns all tokens from source.
func tokenize(source, sourceName string) ([]token, error) {
	l := newLexer(source, sourceName)
	var tokens []token
	for {
		tok, err := l.nextToken()
		if err != nil {
			return nil, err
		}
		tokens = append(tokens, tok)
		if tok.typ == tokEOF {
			break
		}
	}
	return tokens, nil
}

// splitTaggedLiteral splits "tag\"content\"" into (tag, "content")
func splitTaggedLiteral(s string) (string, string) {
	idx := strings.Index(s, `"`)
	if idx <= 0 {
		return "", s
	}
	return s[:idx], s[idx:]
}
