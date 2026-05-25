package reader

import (
	"testing"
)

func assertFormsEqual(t *testing.T, expected, actual []Form) {
	t.Helper()
	if len(expected) != len(actual) {
		t.Fatalf("form count mismatch: expected %d, got %d\nexpected: %v\nactual: %v", len(expected), len(actual), expected, actual)
	}
	for i := range expected {
		if !expected[i].Equal(actual[i]) {
			t.Errorf("form[%d] mismatch:\n  expected: %s\n  actual:   %s", i, debugForm(expected[i]), debugForm(actual[i]))
		}
	}
}

func assertFormEqual(t *testing.T, expected, actual Form) {
	t.Helper()
	if !expected.Equal(actual) {
		t.Errorf("form mismatch:\n  expected: %s\n  actual:   %s", debugForm(expected), debugForm(actual))
	}
}

func debugForm(form Form) string {
	return Write(form)
}

// === Symbol tests (matching test_reader_symbols.py) ===

func TestBareSymbols(t *testing.T) {
	result, err := Read("abc + 1 true nil :size ///path a.b a/b model:gpt-4.1", "")
	if err != nil {
		t.Fatal(err)
	}
	expected := []Form{
		Sym("abc"),
		Sym("+"),
		Sym("1"),
		Sym("true"),
		Sym("nil"),
		Sym(":size"),
		Sym("///path"),
		Sym("a.b"),
		Sym("a/b"),
		Sym("model:gpt-4.1"),
	}
	assertFormsEqual(t, expected, result)
}

func TestQuotedStringIsStringSymbol(t *testing.T) {
	result, err := Read(`abc "abc" "(not a list)" "hello world" ":size"`, "")
	if err != nil {
		t.Fatal(err)
	}
	expected := []Form{
		Sym("abc"),
		Sym(`"abc"`),
		Sym(`"(not a list)"`),
		Sym(`"hello world"`),
		Sym(`":size"`),
	}
	assertFormsEqual(t, expected, result)
}

func TestQuotedStringPreservesRawEscapes(t *testing.T) {
	result, err := Read(`"hello\nworld" "quote: \"" "slash: \\"`, "")
	if err != nil {
		t.Fatal(err)
	}
	expected := []Form{
		Sym(`"hello\nworld"`),
		Sym(`"quote: \""`),
		Sym(`"slash: \\"`),
	}
	assertFormsEqual(t, expected, result)
}

func TestRawQuotedStringKeepsRawPrefix(t *testing.T) {
	result, err := Read(`r"\d+\s+" R"C:\path\to\file"`, "")
	if err != nil {
		t.Fatal(err)
	}
	expected := []Form{
		Sym(`r"\d+\s+"`),
		Sym(`R"C:\path\to\file"`),
	}
	assertFormsEqual(t, expected, result)
}

func TestMultilineStrings(t *testing.T) {
	result, err := Read("\"\"\"hello\nworld\"\"\" r\"\"\"\\d+\\s+\nC:\\path\"\"\"", "")
	if err != nil {
		t.Fatal(err)
	}
	expected := []Form{
		Sym("\"\"\"hello\nworld\"\"\""),
		Sym("r\"\"\"\\d+\\s+\nC:\\path\"\"\""),
	}
	assertFormsEqual(t, expected, result)
}

func TestTaggedLiteralsExpandToTaggedQuoteCalls(t *testing.T) {
	result, err := Read("t\"hello {name}\" sql\"\"\"select *\nfrom docs\"\"\"", "")
	if err != nil {
		t.Fatal(err)
	}
	expected := []Form{
		L(Sym("t"), L(Sym("quote"), Sym(`"hello {name}"`))),
		L(Sym("sql"), L(Sym("quote"), Sym("\"\"\"select *\nfrom docs\"\"\""))),
	}
	assertFormsEqual(t, expected, result)
}

func TestTaggedLiteralsKeepRawEscapes(t *testing.T) {
	result, err := Read(`t"hello\n{name}"`, "")
	if err != nil {
		t.Fatal(err)
	}
	expected := []Form{
		L(Sym("t"), L(Sym("quote"), Sym(`"hello\n{name}"`))),
	}
	assertFormsEqual(t, expected, result)
}

// === Form tests (matching test_reader_forms.py) ===

func TestRawReaderKeepsSurfaceSymbols(t *testing.T) {
	result, err := ReadRaw("'abc '(+ 1 2) ,x ,@xs", "")
	if err != nil {
		t.Fatal(err)
	}
	expected := []Form{
		Sym("'abc"),
		Sym("'"),
		L(Sym("+"), Sym("1"), Sym("2")),
		Sym(",x"),
		Sym(",@xs"),
	}
	assertFormsEqual(t, expected, result)
}

func TestDefaultSurfaceKeepsCommaSymbolsOutsideQuasiquote(t *testing.T) {
	result, err := Read("(define , 10) (1 ,x) (, 1 2)", "")
	if err != nil {
		t.Fatal(err)
	}
	expected := []Form{
		L(Sym("define"), Sym(","), Sym("10")),
		L(Sym("1"), Sym(",x")),
		L(Sym(","), Sym("1"), Sym("2")),
	}
	assertFormsEqual(t, expected, result)
}

func TestDefaultSurfaceExpandsUnquoteSymbolsInsideQuasiquote(t *testing.T) {
	result, err := Read("(quasiquote (,x ,@xs , ,@))", "")
	if err != nil {
		t.Fatal(err)
	}
	expected := []Form{
		L(
			Sym("quasiquote"),
			L(
				L(Sym("unquote"), Sym("x")),
				L(Sym("unquote-splicing"), Sym("xs")),
				Sym(","),
				Sym(",@"),
			),
		),
	}
	assertFormsEqual(t, expected, result)
}

func TestDefineTargetIsNotSurfaceExpanded(t *testing.T) {
	result, err := Read("(define 'x 1) (define ' 2)", "")
	if err != nil {
		t.Fatal(err)
	}
	expected := []Form{
		L(Sym("define"), Sym("'x"), Sym("1")),
		L(Sym("define"), Sym("'"), Sym("2")),
	}
	assertFormsEqual(t, expected, result)
}

func TestExpandSurfaceDialectIsPureFunction(t *testing.T) {
	raw, err := ReadRaw("'abc (+ 1 2)", "")
	if err != nil {
		t.Fatal(err)
	}
	result := ExpandSurfaceDialect(raw)
	expected := []Form{
		L(Sym("quote"), Sym("abc")),
		L(Sym("+"), Sym("1"), Sym("2")),
	}
	assertFormsEqual(t, expected, result)
}

func TestDottedPairForms(t *testing.T) {
	form, err := ReadOne("(a . b)", "")
	if err != nil {
		t.Fatal(err)
	}
	chain, ok := form.(*Chain)
	if !ok {
		t.Fatalf("expected *Chain, got %T", form)
	}
	assertFormEqual(t, Sym("a"), chain.Head)
	assertFormEqual(t, Sym("b"), chain.Tail)
}

func TestInvalidDottedPairFormsAreRejected(t *testing.T) {
	_, err := ReadOne("(. b)", "")
	if err == nil {
		t.Fatal("expected error for (. b)")
	}
	_, ok := err.(*SyntaxError)
	if !ok {
		t.Fatalf("expected *SyntaxError, got %T: %v", err, err)
	}
}

func TestFormsKeepSourceSpans(t *testing.T) {
	form, err := ReadOne("(+ 1\n 2)", "")
	if err != nil {
		t.Fatal(err)
	}
	chain, ok := form.(*Chain)
	if !ok {
		t.Fatalf("expected *Chain, got %T", form)
	}
	formSpan := chain.GetSpan()
	if formSpan == nil {
		t.Fatal("form span is nil")
	}
	if formSpan.StartLine != 1 || formSpan.StartColumn != 1 {
		t.Errorf("form span start: expected 1:1, got %d:%d", formSpan.StartLine, formSpan.StartColumn)
	}

	items := chain.ToSlice()
	if len(items) < 3 {
		t.Fatalf("expected at least 3 items, got %d", len(items))
	}
	lastSpan := items[2].GetSpan()
	if lastSpan == nil {
		t.Fatal("last item span is nil")
	}
	if lastSpan.StartLine != 2 || lastSpan.StartColumn != 2 {
		t.Errorf("last item span start: expected 2:2, got %d:%d", lastSpan.StartLine, lastSpan.StartColumn)
	}
}

func TestReadOneRequiresExactlyOneForm(t *testing.T) {
	_, err := ReadOne("", "")
	if err == nil {
		t.Fatal("expected error for empty input")
	}
	_, err = ReadOne("a b", "")
	if err == nil {
		t.Fatal("expected error for two forms")
	}
}

// === Additional tests ===

func TestNestedLists(t *testing.T) {
	result, err := Read("(a (b c) d)", "")
	if err != nil {
		t.Fatal(err)
	}
	expected := []Form{
		L(Sym("a"), L(Sym("b"), Sym("c")), Sym("d")),
	}
	assertFormsEqual(t, expected, result)
}

func TestEmptyList(t *testing.T) {
	result, err := Read("()", "")
	if err != nil {
		t.Fatal(err)
	}
	if len(result) != 1 {
		t.Fatalf("expected 1 form, got %d", len(result))
	}
	if !IsNil(result[0]) {
		t.Errorf("expected nil for empty list, got %T", result[0])
	}
}

func TestComments(t *testing.T) {
	result, err := Read("; this is a comment\nabc ; inline\n  def", "")
	if err != nil {
		t.Fatal(err)
	}
	expected := []Form{Sym("abc"), Sym("def")}
	assertFormsEqual(t, expected, result)
}

func TestUnclosedParen(t *testing.T) {
	_, err := Read("(a b", "")
	if err == nil {
		t.Fatal("expected error for unclosed paren")
	}
}

func TestUnexpectedCloseParen(t *testing.T) {
	_, err := Read(")", "")
	if err == nil {
		t.Fatal("expected error for unexpected close paren")
	}
}

func TestLeadingQuoteExpansion(t *testing.T) {
	result, err := Read("'hello '(a b c)", "")
	if err != nil {
		t.Fatal(err)
	}
	expected := []Form{
		L(Sym("quote"), Sym("hello")),
		L(Sym("quote"), L(Sym("a"), Sym("b"), Sym("c"))),
	}
	assertFormsEqual(t, expected, result)
}

func TestQuasiquoteWithUnquote(t *testing.T) {
	result, err := Read("(quasiquote (a ,b ,@c))", "")
	if err != nil {
		t.Fatal(err)
	}
	expected := []Form{
		L(Sym("quasiquote"), L(
			Sym("a"),
			L(Sym("unquote"), Sym("b")),
			L(Sym("unquote-splicing"), Sym("c")),
		)),
	}
	assertFormsEqual(t, expected, result)
}

func TestWriteRoundTrip(t *testing.T) {
	cases := []string{
		"(+ 1 2)",
		"(define x 42)",
		"(a . b)",
		"(lambda (x) (+ x 1))",
	}
	for _, src := range cases {
		form, err := ReadOne(src, "")
		if err != nil {
			t.Fatalf("read %q: %v", src, err)
		}
		out := Write(form)
		form2, err := ReadOne(out, "")
		if err != nil {
			t.Fatalf("re-read %q (from %q): %v", out, src, err)
		}
		if !form.Equal(form2) {
			t.Errorf("round-trip mismatch for %q: got %q", src, out)
		}
	}
}

func TestDottedPairMultipleHeads(t *testing.T) {
	form, err := ReadOne("(a b . c)", "")
	if err != nil {
		t.Fatal(err)
	}
	chain, ok := form.(*Chain)
	if !ok {
		t.Fatalf("expected *Chain, got %T", form)
	}
	// (a b . c) = cons(a, cons(b, c))
	assertFormEqual(t, Sym("a"), chain.Head)
	inner, ok := chain.Tail.(*Chain)
	if !ok {
		t.Fatalf("expected inner Chain, got %T", chain.Tail)
	}
	assertFormEqual(t, Sym("b"), inner.Head)
	assertFormEqual(t, Sym("c"), inner.Tail)
}

func TestLambdaBodyNotExpanded(t *testing.T) {
	result, err := Read("(lambda (x) 'x)", "")
	if err != nil {
		t.Fatal(err)
	}
	expected := []Form{
		L(Sym("lambda"), L(Sym("x")), L(Sym("quote"), Sym("x"))),
	}
	assertFormsEqual(t, expected, result)
}

func TestDefunParamsNotExpanded(t *testing.T) {
	result, err := Read("(defun f (a b) 'a)", "")
	if err != nil {
		t.Fatal(err)
	}
	expected := []Form{
		L(Sym("defun"), Sym("f"), L(Sym("a"), Sym("b")), L(Sym("quote"), Sym("a"))),
	}
	assertFormsEqual(t, expected, result)
}

func TestLetBindingsExpanded(t *testing.T) {
	result, err := Read("(let ((x 'a)) x)", "")
	if err != nil {
		t.Fatal(err)
	}
	expected := []Form{
		L(Sym("let"), L(L(Sym("x"), L(Sym("quote"), Sym("a")))), Sym("x")),
	}
	assertFormsEqual(t, expected, result)
}
