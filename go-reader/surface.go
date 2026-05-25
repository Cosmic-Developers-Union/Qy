package reader

import "strings"

// ExpandSurfaceDialect transforms reader sugar into canonical forms:
// - 'x (prefix quote) -> (quote x)
// - 'x (leading-quote symbol) -> (quote x)
// - ,x inside quasiquote -> (unquote x)
// - ,@x inside quasiquote -> (unquote-splicing x)
func ExpandSurfaceDialect(forms []Form) []Form {
	return expandProgram(forms)
}

func expandProgram(forms []Form) []Form {
	seq := expandSequence(forms, false)
	return seq
}

func expandForm(form Form, inQuasiquote bool) Form {
	switch f := form.(type) {
	case Symbol:
		return expandSymbol(f, inQuasiquote)
	case *Chain:
		return expandChain(f, inQuasiquote)
	case Nil:
		return f
	default:
		return form
	}
}

func expandSymbol(sym Symbol, inQuasiquote bool) Form {
	if strings.HasPrefix(sym.Name, "'") && len(sym.Name) > 1 {
		quoted := Symbol{Name: sym.Name[1:], Span: sym.Span}
		return surfaceCall("quote", []Form{expandForm(quoted, inQuasiquote)}, sym.Span)
	}
	if inQuasiquote && strings.HasPrefix(sym.Name, ",@") && len(sym.Name) > 2 {
		inner := Symbol{Name: sym.Name[2:], Span: sym.Span}
		return surfaceCall("unquote-splicing", []Form{expandForm(inner, false)}, sym.Span)
	}
	if inQuasiquote && strings.HasPrefix(sym.Name, ",") && len(sym.Name) > 1 && !strings.HasPrefix(sym.Name, ",@") {
		inner := Symbol{Name: sym.Name[1:], Span: sym.Span}
		return surfaceCall("unquote", []Form{expandForm(inner, false)}, sym.Span)
	}
	return sym
}

func expandChain(chain *Chain, inQuasiquote bool) Form {
	if IsNil(chain) {
		return chain
	}

	head := Car(chain)
	sym, isSym := head.(Symbol)
	if !isSym {
		return expandChainSequence(chain, inQuasiquote)
	}

	switch sym.Name {
	case "define":
		return expandDefine(chain, inQuasiquote)
	case "defun", "macro":
		return expandNamedBody(chain, inQuasiquote)
	case "lambda":
		return expandLambda(chain, inQuasiquote)
	case "let":
		return expandLet(chain, inQuasiquote)
	case "defeffect", "exports", "from", "import":
		return chain
	case "module":
		return expandModule(chain, inQuasiquote)
	case "quasiquote":
		return expandQuasiquote(chain, inQuasiquote)
	}

	return expandChainSequence(chain, inQuasiquote)
}

func expandChainSequence(chain Form, inQuasiquote bool) Form {
	if IsNil(chain) {
		return chain
	}

	span := GetSpan(chain)
	var expanded []Form
	current := chain

	for IsChain(current) {
		head := Car(current)
		tail := Cdr(current)

		// Check prefix quote: ' followed by adjacent form
		if sym, ok := head.(Symbol); ok && sym.Name == "'" && IsChain(tail) && formsAreAdjacent(head, Car(tail)) {
			quotedForm := Car(tail)
			expanded = append(expanded, surfaceCall("quote", []Form{expandForm(quotedForm, inQuasiquote)}, combineSpans(head, quotedForm)))
			current = Cdr(tail)
			continue
		}

		// Check prefix quasiquote: ` followed by adjacent form
		if sym, ok := head.(Symbol); ok && sym.Name == "`" && IsChain(tail) && formsAreAdjacent(head, Car(tail)) {
			qqForm := Car(tail)
			expanded = append(expanded, surfaceCall("quasiquote", []Form{expandForm(qqForm, true)}, combineSpans(head, qqForm)))
			current = Cdr(tail)
			continue
		}

		expanded = append(expanded, expandForm(head, inQuasiquote))
		current = tail
	}

	// Handle improper list tail
	if !IsNil(current) {
		result := expandForm(current, inQuasiquote)
		for i := len(expanded) - 1; i >= 0; i-- {
			result = Cons(expanded[i], result, span)
		}
		return result
	}

	return ListToChain(expanded, span)
}

func expandSequence(forms []Form, inQuasiquote bool) []Form {
	var expanded []Form
	i := 0
	for i < len(forms) {
		form := forms[i]

		// prefix quote
		if sym, ok := form.(Symbol); ok && sym.Name == "'" && i+1 < len(forms) && formsAreAdjacent(form, forms[i+1]) {
			expanded = append(expanded, surfaceCall("quote", []Form{expandForm(forms[i+1], inQuasiquote)}, combineSpans(form, forms[i+1])))
			i += 2
			continue
		}

		// prefix quasiquote
		if sym, ok := form.(Symbol); ok && sym.Name == "`" && i+1 < len(forms) && formsAreAdjacent(form, forms[i+1]) {
			expanded = append(expanded, surfaceCall("quasiquote", []Form{expandForm(forms[i+1], true)}, combineSpans(form, forms[i+1])))
			i += 2
			continue
		}

		expanded = append(expanded, expandForm(form, inQuasiquote))
		i++
	}
	return expanded
}

func expandDefine(chain *Chain, inQuasiquote bool) Form {
	items, tail := ChainToSlice(chain)
	if !IsNil(tail) || len(items) <= 2 {
		return chain
	}
	span := GetSpan(chain)

	var expandedName Form
	if inQuasiquote {
		expandedName = expandForm(items[1], inQuasiquote)
	} else {
		expandedName = items[1]
	}

	expandedValues := expandSequence(items[2:], inQuasiquote)
	all := make([]Form, 0, 2+len(expandedValues))
	all = append(all, items[0], expandedName)
	all = append(all, expandedValues...)
	return ListToChain(all, span)
}

func expandNamedBody(chain *Chain, inQuasiquote bool) Form {
	items, tail := ChainToSlice(chain)
	if !IsNil(tail) || len(items) <= 3 {
		return chain
	}
	span := GetSpan(chain)

	expandedBody := expandSequence(items[3:], inQuasiquote)
	all := make([]Form, 0, 3+len(expandedBody))
	all = append(all, items[0], items[1], items[2])
	all = append(all, expandedBody...)
	return ListToChain(all, span)
}

func expandLambda(chain *Chain, inQuasiquote bool) Form {
	items, tail := ChainToSlice(chain)
	if !IsNil(tail) || len(items) <= 2 {
		return chain
	}
	span := GetSpan(chain)

	var expandedArgs Form
	if inQuasiquote {
		expandedArgs = expandForm(items[1], inQuasiquote)
	} else {
		expandedArgs = items[1]
	}

	expandedBody := expandSequence(items[2:], inQuasiquote)
	all := make([]Form, 0, 2+len(expandedBody))
	all = append(all, items[0], expandedArgs)
	all = append(all, expandedBody...)
	return ListToChain(all, span)
}

func expandModule(chain *Chain, inQuasiquote bool) Form {
	items, tail := ChainToSlice(chain)
	if !IsNil(tail) || len(items) <= 2 {
		return chain
	}
	span := GetSpan(chain)

	expandedBody := make([]Form, len(items[2:]))
	for i, item := range items[2:] {
		expandedBody[i] = expandForm(item, inQuasiquote)
	}
	all := make([]Form, 0, 2+len(expandedBody))
	all = append(all, items[0], items[1])
	all = append(all, expandedBody...)
	return ListToChain(all, span)
}

func expandQuasiquote(chain *Chain, inQuasiquote bool) Form {
	items, tail := ChainToSlice(chain)
	if !IsNil(tail) {
		return chain
	}
	span := GetSpan(chain)
	if len(items) != 2 {
		expandedItems := make([]Form, len(items))
		for i, item := range items {
			expandedItems[i] = expandForm(item, inQuasiquote)
		}
		return ListToChain(expandedItems, span)
	}
	return ListToChain([]Form{items[0], expandForm(items[1], true)}, span)
}

func expandLet(chain *Chain, inQuasiquote bool) Form {
	items, tail := ChainToSlice(chain)
	if !IsNil(tail) || len(items) <= 2 {
		return chain
	}
	span := GetSpan(chain)

	bindings := items[1]
	if IsChain(bindings) {
		bindingItems, bindingTail := ChainToSlice(bindings)
		if IsNil(bindingTail) {
			expandedBindings := make([]Form, len(bindingItems))
			for i, binding := range bindingItems {
				if IsChain(binding) {
					bItems, bTail := ChainToSlice(binding)
					if IsNil(bTail) && len(bItems) > 1 {
						valuesChain := ListToChain(bItems[1:], nil)
						expandedValuesChain := expandChainSequence(valuesChain, inQuasiquote)
						var expandedValues []Form
						if IsChain(expandedValuesChain) {
							evItems, _ := ChainToSlice(expandedValuesChain)
							expandedValues = evItems
						} else {
							expandedValues = []Form{expandedValuesChain}
						}
						all := make([]Form, 0, 1+len(expandedValues))
						all = append(all, bItems[0])
						all = append(all, expandedValues...)
						expandedBindings[i] = ListToChain(all, GetSpan(binding))
					} else {
						expandedBindings[i] = binding
					}
				} else {
					expandedBindings[i] = binding
				}
			}
			bindings = ListToChain(expandedBindings, GetSpan(items[1]))
		}
	}

	expandedBody := make([]Form, len(items[2:]))
	for i, item := range items[2:] {
		expandedBody[i] = expandForm(item, inQuasiquote)
	}

	all := make([]Form, 0, 2+len(expandedBody))
	all = append(all, items[0], bindings)
	all = append(all, expandedBody...)
	return ListToChain(all, span)
}

func surfaceCall(name string, args []Form, span *SourceSpan) Form {
	items := make([]Form, 0, 1+len(args))
	items = append(items, Symbol{Name: name, Span: span})
	items = append(items, args...)
	return ListToChain(items, span)
}

func formsAreAdjacent(left, right Form) bool {
	leftSpan := GetSpan(left)
	rightSpan := GetSpan(right)

	// Special case: nil (empty list) with no span after a form
	if IsNil(right) && rightSpan == nil && leftSpan != nil {
		return true
	}

	return leftSpan != nil && rightSpan != nil &&
		leftSpan.Source == rightSpan.Source &&
		leftSpan.EndLine == rightSpan.StartLine &&
		leftSpan.EndColumn == rightSpan.StartColumn
}

func combineSpans(left, right Form) *SourceSpan {
	leftSpan := GetSpan(left)
	rightSpan := GetSpan(right)
	if leftSpan == nil {
		return rightSpan
	}
	if rightSpan == nil {
		return leftSpan
	}
	if leftSpan.Source != rightSpan.Source {
		return leftSpan
	}
	return &SourceSpan{
		Source:      leftSpan.Source,
		StartLine:   leftSpan.StartLine,
		StartColumn: leftSpan.StartColumn,
		EndLine:     rightSpan.EndLine,
		EndColumn:   rightSpan.EndColumn,
	}
}
