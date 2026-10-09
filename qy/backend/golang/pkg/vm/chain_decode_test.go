package vm

import "testing"

// improper chain 的 tail 是值载荷（{type,value}），不是链节点；解码时不能
// 误当 {head,tail} 节点，否则会得到 Chain(nil, QyNil)。
func TestDecodeChainPayloadImproperTail(t *testing.T) {
	payload := map[string]interface{}{
		"head": map[string]interface{}{"type": "symbol", "value": "a"},
		"tail": map[string]interface{}{"type": "symbol", "value": "1"},
	}
	value := decodeChainPayload(payload)
	chain, ok := value.(*Chain)
	if !ok {
		t.Fatalf("expected *Chain, got %T", value)
	}
	head, ok := chain.Head.(*Symbol)
	if !ok || head.Name != "a" {
		t.Fatalf("head = %#v", chain.Head)
	}
	tail, ok := chain.Tail.(*Symbol)
	if !ok || tail.Name != "1" {
		t.Fatalf("improper tail = %#v (want Symbol \"1\")", chain.Tail)
	}
}
