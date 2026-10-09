package stdlib

import (
	"testing"

	"github.com/Cosmic-Developers-Union/Qy/qy/backend/golang/pkg/vm"
)

// TestTypeNameOfQyLabels 守卫「类型标签与 Python `qy.sem.classify.value_type` 一致」。
func TestTypeNameOfQyLabels(t *testing.T) {
	cases := []struct {
		value vm.Value
		want  string
	}{
		{vm.NewString("a"), "string"},
		{vm.NewChar("a"), "char"},
		{vm.NewSymbol("s"), "symbol"},
		{vm.NewTuple(nil), "tuple"},
		{vm.NewList(nil), "list"},
		{vm.NewDict(nil), "dict"},
		{vm.NewSet(nil), "set"},
		{vm.QyNil, "nil"},
	}
	for _, c := range cases {
		if got := typeNameOf(c.value); got != c.want {
			t.Errorf("typeNameOf(%v) = %q, want %q", c.value, got, c.want)
		}
	}
}

// TestOptionalStringTreatsHostNil 守卫「缺省参数（宿主 nil）视为未提供」。
func TestOptionalStringTreatsHostNil(t *testing.T) {
	if _, present := optionalString(nil); present {
		t.Errorf("optionalString(nil) present = true, want false")
	}
	if _, present := optionalString(vm.QyNil); present {
		t.Errorf("optionalString(QyNil) present = true, want false")
	}
	if v, present := optionalString(vm.NewString("x")); !present || v == nil {
		t.Errorf("optionalString(StringValue) = %v, %v; want value, true", v, present)
	}
}

// TestStringSplitWithoutSeparator 守卫缺省 separator 的 whitespace split。
func TestStringSplitWithoutSeparator(t *testing.T) {
	result, err := StringSplit(vm.NewString("a b  c"), nil)
	if err != nil {
		t.Fatalf("StringSplit returned error: %v", err)
	}
	tuple, ok := result.(*vm.TupleValue)
	if !ok || len(tuple.Items) != 3 {
		t.Fatalf("StringSplit = %v, want 3 items", result)
	}
}
