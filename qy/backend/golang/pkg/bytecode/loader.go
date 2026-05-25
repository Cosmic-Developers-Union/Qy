package bytecode

import (
	"encoding/json"
	"fmt"
	"os"
)

func LoadFile(path string) (*Program, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("read bytecode file: %w", err)
	}
	return Load(data)
}

func Load(data []byte) (*Program, error) {
	var prog Program
	if err := json.Unmarshal(data, &prog); err != nil {
		return nil, fmt.Errorf("parse bytecode JSON: %w", err)
	}
	if prog.Version != 1 {
		return nil, fmt.Errorf("unsupported bytecode version: %d", prog.Version)
	}
	return &prog, nil
}
