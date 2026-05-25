package reader

import (
	"testing"
)

// TestCrossValidation verifies that the Go reader produces the same
// output as the Python reader for a set of representative inputs.
func TestCrossValidation(t *testing.T) {
	cases := []struct {
		input    string
		expected string
	}{
		{"(+ 1 2)", "(+ 1 2)"},
		{"(define x 42)", "(define x 42)"},
		{"'hello", "'hello"},
		{"'(a b c)", "'(a b c)"},
		{"(a . b)", "(a . b)"},
		{"(a b . c)", "(a b . c)"},
		{"(quasiquote (,x ,@xs , ,@))", "`((unquote x) (unquote-splicing xs) , ,@)"},
		{"(define 'x 1)", "(define \"'x\" 1)"},
		{"(lambda (x) 'x)", "(lambda (x) 'x)"},
		{"(defun f (a b) 'a)", "(defun f (a b) 'a)"},
		{"(let ((x 'a)) x)", "(let ((x 'a)) x)"},
		{"t\"hello {name}\"", "(t '\"hello {name}\")"},
		{"; comment\nabc", "abc"},
	}

	for _, tc := range cases {
		forms, err := Read(tc.input, "")
		if err != nil {
			t.Errorf("Read(%q): %v", tc.input, err)
			continue
		}
		got := WriteProgram(forms)
		if got != tc.expected {
			t.Errorf("Read(%q):\n  got:      %q\n  expected: %q", tc.input, got, tc.expected)
		}
	}
}
