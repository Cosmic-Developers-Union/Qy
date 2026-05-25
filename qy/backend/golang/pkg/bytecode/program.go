package bytecode

type Program struct {
	Version         int               `json:"version"`
	Main            int               `json:"main"`
	Functions       []Function        `json:"functions"`
	HygieneBindings map[string]string `json:"hygiene_bindings,omitempty"`
}

type Function struct {
	Name          string        `json:"name"`
	Params        []string      `json:"params"`
	RegisterCount int           `json:"register_count"`
	Instructions  []Instruction `json:"instructions"`
}

type Instruction struct {
	Opcode   string    `json:"opcode"`
	Operands []Operand `json:"operands"`
}

type Operand struct {
	Type  string      `json:"type"`
	Value interface{} `json:"value"`
}

type HandlerSpec struct {
	Effect    string `json:"effect"`
	HandlerFn int    `json:"handler_fn"`
}

type ImportSpec struct {
	Name  string `json:"name"`
	Alias string `json:"alias"`
}

func (o *Operand) AsReg() int {
	return toInt(o.Value)
}

func (o *Operand) AsInt() int {
	return toInt(o.Value)
}

func (o *Operand) AsFloat() float64 {
	switch v := o.Value.(type) {
	case float64:
		return v
	case int:
		return float64(v)
	}
	return 0
}

func (o *Operand) AsString() string {
	if s, ok := o.Value.(string); ok {
		return s
	}
	return ""
}

func (o *Operand) AsBool() bool {
	switch v := o.Value.(type) {
	case bool:
		return v
	case float64:
		return v != 0
	case int:
		return v != 0
	}
	return false
}

func (o *Operand) AsRegTuple() []int {
	switch v := o.Value.(type) {
	case []interface{}:
		result := make([]int, len(v))
		for i, item := range v {
			result[i] = toInt(item)
		}
		return result
	case []int:
		return v
	}
	return nil
}

func (o *Operand) AsHandlerSpecs() []HandlerSpec {
	arr, ok := o.Value.([]interface{})
	if !ok {
		return nil
	}
	specs := make([]HandlerSpec, 0, len(arr))
	for _, item := range arr {
		m, ok := item.(map[string]interface{})
		if !ok {
			continue
		}
		specs = append(specs, HandlerSpec{
			Effect:    m["effect"].(string),
			HandlerFn: toInt(m["handler_fn"]),
		})
	}
	return specs
}

func (o *Operand) AsImportSpecs() []ImportSpec {
	arr, ok := o.Value.([]interface{})
	if !ok {
		return nil
	}
	specs := make([]ImportSpec, 0, len(arr))
	for _, item := range arr {
		m, ok := item.(map[string]interface{})
		if !ok {
			continue
		}
		specs = append(specs, ImportSpec{
			Name:  m["name"].(string),
			Alias: m["alias"].(string),
		})
	}
	return specs
}

func (o *Operand) AsSymbolTuple() []string {
	arr, ok := o.Value.([]interface{})
	if !ok {
		return nil
	}
	result := make([]string, len(arr))
	for i, item := range arr {
		result[i] = item.(string)
	}
	return result
}

func toInt(v interface{}) int {
	switch n := v.(type) {
	case float64:
		return int(n)
	case int:
		return n
	case int64:
		return int(n)
	}
	return 0
}
