package bytecode

import (
	"encoding/json"
	"fmt"
	"os"
)

// LoadFile 从文件装载字节码程序。
func LoadFile(path string) (*Program, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("read bytecode file: %w", err)
	}
	return Load(data)
}

// Load 从 JSON 文本装载字节码程序（对应 `load_bytecode_json`）。
func Load(data []byte) (*Program, error) {
	var prog Program
	if err := json.Unmarshal(data, &prog); err != nil {
		return nil, fmt.Errorf("parse bytecode JSON: %w", err)
	}
	if prog.Version != 1 {
		return nil, fmt.Errorf("unsupported bytecode JSON version: %d", prog.Version)
	}
	return &prog, nil
}
