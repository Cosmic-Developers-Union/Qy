package stdlib

import "testing"

// 对齐 Python `str.upper()`/`str.lower()`（含多字符展开与 Final_Sigma）。
func TestFullCaseMappingMatchesPython(t *testing.T) {
	cases := []struct {
		input string
		upper string
		lower string
	}{
		{"ß", "SS", "ß"},
		{"straße", "STRASSE", "straße"},
		{"ﬁ", "FI", "ﬁ"},
		{"İ", "İ", "i̇"},
		{"ǰ", "J̌", "ǰ"},
		{"ŉ", "ʼN", "ŉ"},
		{"ΑΣ", "ΑΣ", "ας"},
		{"ΟΔΟΣ", "ΟΔΟΣ", "οδος"},
		{"ΣΣ", "ΣΣ", "σς"},
		{"ΑΣΑ", "ΑΣΑ", "ασα"},
		{"ΑΣΑΣ", "ΑΣΑΣ", "ασας"},
		{"Σ", "Σ", "σ"},
		{"1Σ", "1Σ", "1σ"},
		{"한글", "한글", "한글"},
		{"abc123", "ABC123", "abc123"},
	}
	for _, tc := range cases {
		if got := fullUpper(tc.input); got != tc.upper {
			t.Errorf("fullUpper(%q) = %q, want %q", tc.input, got, tc.upper)
		}
		if got := fullLower(tc.input); got != tc.lower {
			t.Errorf("fullLower(%q) = %q, want %q", tc.input, got, tc.lower)
		}
	}
}
