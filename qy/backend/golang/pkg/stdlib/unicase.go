package stdlib

import (
	"strings"
	"unicode"
)

// Full Unicode case mapping（对齐 Python `str.upper()`/`str.lower()` 与 JS
// `toUpperCase`/`toLowerCase`）。
//
// Go 标准库只有 simple case mapping（`unicode.ToUpper`/`ToLower`），与本仓库
// 的参考实现（Python 3.12 的 Unicode 15.0）不一致：
//   - 多字符展开（ß -> SS、ﬁ -> FI、İ -> i̇ …）；
//   - Unicode 版本差异（Go 1.27 用 Unicode 17.0，Python 3.12 用 15.0）；
//   - 希腊 sigma 的 Final_Sigma 上下文规则。
//
// fullUpperTable/fullLowerTable 由「Python `str.upper()`/`lower()` 与 Go simple
// mapping 的逐码点差集」生成，覆盖前两类；Final_Sigma 由 fullLower 现场判定。
// 生成方式：用 Go 转储每个码点的 unicode.ToUpper/ToLower，与 Python
// chr(c).upper()/lower() 比较，把不同的码点写成下面的表。Python 侧 Unicode
// 版本升级后需重新生成。

var fullUpperTable = map[rune]string{
	0x00DF:  "SS",
	0x0149:  "\u02bcN",
	0x019B:  "\u019b",
	0x01F0:  "J\u030c",
	0x0264:  "\u0264",
	0x0390:  "\u0399\u0308\u0301",
	0x03B0:  "\u03a5\u0308\u0301",
	0x0587:  "\u0535\u0552",
	0x1C8A:  "\u1c8a",
	0x1E96:  "H\u0331",
	0x1E97:  "T\u0308",
	0x1E98:  "W\u030a",
	0x1E99:  "Y\u030a",
	0x1E9A:  "A\u02be",
	0x1F50:  "\u03a5\u0313",
	0x1F52:  "\u03a5\u0313\u0300",
	0x1F54:  "\u03a5\u0313\u0301",
	0x1F56:  "\u03a5\u0313\u0342",
	0x1F80:  "\u1f08\u0399",
	0x1F81:  "\u1f09\u0399",
	0x1F82:  "\u1f0a\u0399",
	0x1F83:  "\u1f0b\u0399",
	0x1F84:  "\u1f0c\u0399",
	0x1F85:  "\u1f0d\u0399",
	0x1F86:  "\u1f0e\u0399",
	0x1F87:  "\u1f0f\u0399",
	0x1F88:  "\u1f08\u0399",
	0x1F89:  "\u1f09\u0399",
	0x1F8A:  "\u1f0a\u0399",
	0x1F8B:  "\u1f0b\u0399",
	0x1F8C:  "\u1f0c\u0399",
	0x1F8D:  "\u1f0d\u0399",
	0x1F8E:  "\u1f0e\u0399",
	0x1F8F:  "\u1f0f\u0399",
	0x1F90:  "\u1f28\u0399",
	0x1F91:  "\u1f29\u0399",
	0x1F92:  "\u1f2a\u0399",
	0x1F93:  "\u1f2b\u0399",
	0x1F94:  "\u1f2c\u0399",
	0x1F95:  "\u1f2d\u0399",
	0x1F96:  "\u1f2e\u0399",
	0x1F97:  "\u1f2f\u0399",
	0x1F98:  "\u1f28\u0399",
	0x1F99:  "\u1f29\u0399",
	0x1F9A:  "\u1f2a\u0399",
	0x1F9B:  "\u1f2b\u0399",
	0x1F9C:  "\u1f2c\u0399",
	0x1F9D:  "\u1f2d\u0399",
	0x1F9E:  "\u1f2e\u0399",
	0x1F9F:  "\u1f2f\u0399",
	0x1FA0:  "\u1f68\u0399",
	0x1FA1:  "\u1f69\u0399",
	0x1FA2:  "\u1f6a\u0399",
	0x1FA3:  "\u1f6b\u0399",
	0x1FA4:  "\u1f6c\u0399",
	0x1FA5:  "\u1f6d\u0399",
	0x1FA6:  "\u1f6e\u0399",
	0x1FA7:  "\u1f6f\u0399",
	0x1FA8:  "\u1f68\u0399",
	0x1FA9:  "\u1f69\u0399",
	0x1FAA:  "\u1f6a\u0399",
	0x1FAB:  "\u1f6b\u0399",
	0x1FAC:  "\u1f6c\u0399",
	0x1FAD:  "\u1f6d\u0399",
	0x1FAE:  "\u1f6e\u0399",
	0x1FAF:  "\u1f6f\u0399",
	0x1FB2:  "\u1fba\u0399",
	0x1FB3:  "\u0391\u0399",
	0x1FB4:  "\u0386\u0399",
	0x1FB6:  "\u0391\u0342",
	0x1FB7:  "\u0391\u0342\u0399",
	0x1FBC:  "\u0391\u0399",
	0x1FC2:  "\u1fca\u0399",
	0x1FC3:  "\u0397\u0399",
	0x1FC4:  "\u0389\u0399",
	0x1FC6:  "\u0397\u0342",
	0x1FC7:  "\u0397\u0342\u0399",
	0x1FCC:  "\u0397\u0399",
	0x1FD2:  "\u0399\u0308\u0300",
	0x1FD3:  "\u0399\u0308\u0301",
	0x1FD6:  "\u0399\u0342",
	0x1FD7:  "\u0399\u0308\u0342",
	0x1FE2:  "\u03a5\u0308\u0300",
	0x1FE3:  "\u03a5\u0308\u0301",
	0x1FE4:  "\u03a1\u0313",
	0x1FE6:  "\u03a5\u0342",
	0x1FE7:  "\u03a5\u0308\u0342",
	0x1FF2:  "\u1ffa\u0399",
	0x1FF3:  "\u03a9\u0399",
	0x1FF4:  "\u038f\u0399",
	0x1FF6:  "\u03a9\u0342",
	0x1FF7:  "\u03a9\u0342\u0399",
	0x1FFC:  "\u03a9\u0399",
	0xA7CD:  "\ua7cd",
	0xA7CF:  "\ua7cf",
	0xA7D3:  "\ua7d3",
	0xA7D5:  "\ua7d5",
	0xA7DB:  "\ua7db",
	0xFB00:  "FF",
	0xFB01:  "FI",
	0xFB02:  "FL",
	0xFB03:  "FFI",
	0xFB04:  "FFL",
	0xFB05:  "ST",
	0xFB06:  "ST",
	0xFB13:  "\u0544\u0546",
	0xFB14:  "\u0544\u0535",
	0xFB15:  "\u0544\u053b",
	0xFB16:  "\u054e\u0546",
	0xFB17:  "\u0544\u053d",
	0x10D70: "\U00010d70",
	0x10D71: "\U00010d71",
	0x10D72: "\U00010d72",
	0x10D73: "\U00010d73",
	0x10D74: "\U00010d74",
	0x10D75: "\U00010d75",
	0x10D76: "\U00010d76",
	0x10D77: "\U00010d77",
	0x10D78: "\U00010d78",
	0x10D79: "\U00010d79",
	0x10D7A: "\U00010d7a",
	0x10D7B: "\U00010d7b",
	0x10D7C: "\U00010d7c",
	0x10D7D: "\U00010d7d",
	0x10D7E: "\U00010d7e",
	0x10D7F: "\U00010d7f",
	0x10D80: "\U00010d80",
	0x10D81: "\U00010d81",
	0x10D82: "\U00010d82",
	0x10D83: "\U00010d83",
	0x10D84: "\U00010d84",
	0x10D85: "\U00010d85",
	0x16EBB: "\U00016ebb",
	0x16EBC: "\U00016ebc",
	0x16EBD: "\U00016ebd",
	0x16EBE: "\U00016ebe",
	0x16EBF: "\U00016ebf",
	0x16EC0: "\U00016ec0",
	0x16EC1: "\U00016ec1",
	0x16EC2: "\U00016ec2",
	0x16EC3: "\U00016ec3",
	0x16EC4: "\U00016ec4",
	0x16EC5: "\U00016ec5",
	0x16EC6: "\U00016ec6",
	0x16EC7: "\U00016ec7",
	0x16EC8: "\U00016ec8",
	0x16EC9: "\U00016ec9",
	0x16ECA: "\U00016eca",
	0x16ECB: "\U00016ecb",
	0x16ECC: "\U00016ecc",
	0x16ECD: "\U00016ecd",
	0x16ECE: "\U00016ece",
	0x16ECF: "\U00016ecf",
	0x16ED0: "\U00016ed0",
	0x16ED1: "\U00016ed1",
	0x16ED2: "\U00016ed2",
	0x16ED3: "\U00016ed3",
}

var fullLowerTable = map[rune]string{
	0x0130:  "i\u0307",
	0x1C89:  "\u1c89",
	0xA7CB:  "\ua7cb",
	0xA7CC:  "\ua7cc",
	0xA7CE:  "\ua7ce",
	0xA7D2:  "\ua7d2",
	0xA7D4:  "\ua7d4",
	0xA7DA:  "\ua7da",
	0xA7DC:  "\ua7dc",
	0x10D50: "\U00010d50",
	0x10D51: "\U00010d51",
	0x10D52: "\U00010d52",
	0x10D53: "\U00010d53",
	0x10D54: "\U00010d54",
	0x10D55: "\U00010d55",
	0x10D56: "\U00010d56",
	0x10D57: "\U00010d57",
	0x10D58: "\U00010d58",
	0x10D59: "\U00010d59",
	0x10D5A: "\U00010d5a",
	0x10D5B: "\U00010d5b",
	0x10D5C: "\U00010d5c",
	0x10D5D: "\U00010d5d",
	0x10D5E: "\U00010d5e",
	0x10D5F: "\U00010d5f",
	0x10D60: "\U00010d60",
	0x10D61: "\U00010d61",
	0x10D62: "\U00010d62",
	0x10D63: "\U00010d63",
	0x10D64: "\U00010d64",
	0x10D65: "\U00010d65",
	0x16EA0: "\U00016ea0",
	0x16EA1: "\U00016ea1",
	0x16EA2: "\U00016ea2",
	0x16EA3: "\U00016ea3",
	0x16EA4: "\U00016ea4",
	0x16EA5: "\U00016ea5",
	0x16EA6: "\U00016ea6",
	0x16EA7: "\U00016ea7",
	0x16EA8: "\U00016ea8",
	0x16EA9: "\U00016ea9",
	0x16EAA: "\U00016eaa",
	0x16EAB: "\U00016eab",
	0x16EAC: "\U00016eac",
	0x16EAD: "\U00016ead",
	0x16EAE: "\U00016eae",
	0x16EAF: "\U00016eaf",
	0x16EB0: "\U00016eb0",
	0x16EB1: "\U00016eb1",
	0x16EB2: "\U00016eb2",
	0x16EB3: "\U00016eb3",
	0x16EB4: "\U00016eb4",
	0x16EB5: "\U00016eb5",
	0x16EB6: "\U00016eb6",
	0x16EB7: "\U00016eb7",
	0x16EB8: "\U00016eb8",
}

// fullUpper 对齐 Python `str.upper()`。
func fullUpper(text string) string {
	var builder strings.Builder
	builder.Grow(len(text))
	for _, r := range text {
		if mapped, ok := fullUpperTable[r]; ok {
			builder.WriteString(mapped)
			continue
		}
		builder.WriteRune(unicode.ToUpper(r))
	}
	return builder.String()
}

// fullLower 对齐 Python `str.lower()`（含 Final_Sigma 上下文规则）。
func fullLower(text string) string {
	runes := []rune(text)
	var builder strings.Builder
	builder.Grow(len(text))
	for index, r := range runes {
		if mapped, ok := fullLowerTable[r]; ok {
			builder.WriteString(mapped)
			continue
		}
		if r == 'Σ' && isFinalSigma(runes, index) {
			builder.WriteRune('ς')
			continue
		}
		builder.WriteRune(unicode.ToLower(r))
	}
	return builder.String()
}

// isFinalSigma 判定 runes[index] 处的 sigma 是否应小写为 final sigma（Unicode Final_Sigma 规则）。
func isFinalSigma(runes []rune, index int) bool {
	before := false
	for i := index - 1; i >= 0; i-- {
		r := runes[i]
		if isCaseIgnorable(r) {
			continue
		}
		before = isCased(r)
		break
	}
	if !before {
		return false
	}
	for i := index + 1; i < len(runes); i++ {
		r := runes[i]
		if isCaseIgnorable(r) {
			continue
		}
		return !isCased(r)
	}
	return true
}

func isCased(r rune) bool {
	return unicode.Is(unicode.Lower, r) || unicode.Is(unicode.Upper, r) || unicode.Is(unicode.Title, r)
}

func isCaseIgnorable(r rune) bool {
	if unicode.In(r, unicode.Mn, unicode.Me, unicode.Cf, unicode.Lm, unicode.Sk) {
		return true
	}
	// Unicode Case_Ignorable 中不属于上述分类的少数码点。
	return r == 0x0027 || r == 0x2019
}
