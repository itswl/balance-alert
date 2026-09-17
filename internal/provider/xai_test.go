package provider

import (
	"encoding/binary"
	"math"
	"testing"
)

func TestParseXAIQuota(t *testing.T) {
	percent := make([]byte, 4)
	binary.LittleEndian.PutUint32(percent, math.Float32bits(30))
	inner := append(fieldFixed32(1, percent), fieldBytes(5, fieldVarint(1, 1_800_000_000))...)
	payload := fieldBytes(1, inner)
	frame := append([]byte{0, 0, 0, 0, byte(len(payload))}, payload...)

	got, err := parseXAIQuota(frame)
	if err != nil {
		t.Fatalf("parseXAIQuota() error = %v", err)
	}
	if got != 70 {
		t.Fatalf("remaining quota = %v, want 70", got)
	}
}

func TestParseXAIQuotaRejectsMissingUsage(t *testing.T) {
	payload := fieldBytes(2, []byte{1, 2, 3})
	frame := append([]byte{0, 0, 0, 0, byte(len(payload))}, payload...)
	if _, err := parseXAIQuota(frame); err == nil {
		t.Fatal("expected missing usage percentage to fail")
	}
}

func fieldVarint(number int, value uint64) []byte {
	return append(varint(uint64(number<<3)), varint(value)...)
}

func fieldBytes(number int, value []byte) []byte {
	out := varint(uint64(number<<3 | 2))
	out = append(out, varint(uint64(len(value)))...)
	return append(out, value...)
}

func fieldFixed32(number int, value []byte) []byte {
	return append(varint(uint64(number<<3|5)), value...)
}

func varint(value uint64) []byte {
	var out []byte
	for value >= 0x80 {
		out = append(out, byte(value)|0x80)
		value >>= 7
	}
	return append(out, byte(value))
}
