package provider

import (
	"context"
	"encoding/binary"
	"errors"
	"fmt"
	"io"
	"math"
	"net/http"
	"strings"
)

// xAI's public inference API does not expose account credits as JSON. The
// GrokBuild console currently exposes the subscription quota through this
// gRPC-Web endpoint. Keep this adapter isolated because the endpoint is not a
// stable public API and may change independently of api.x.ai.
const xaiBillingURL = "https://grok.com/grok_api_v2.GrokBuildBilling/GetGrokCreditsConfig"

func init() {
	Register("xai", "xAI", "quota", func(apiKey string, client *Client) (Provider, error) {
		if strings.TrimSpace(apiKey) == "" {
			return nil, errors.New("xAI API key is empty")
		}
		return &xaiProvider{apiKey: apiKey, client: client}, nil
	})
}

type xaiProvider struct {
	apiKey string
	client *Client
}

func (p *xaiProvider) Fetch(ctx context.Context) (float64, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, xaiBillingURL,
		strings.NewReader("\x00\x00\x00\x00\x00"))
	if err != nil {
		return 0, err
	}
	req.Header.Set("Authorization", "Bearer "+p.apiKey)
	req.Header.Set("Content-Type", "application/grpc-web+proto")
	req.Header.Set("x-grpc-web", "1")
	req.Header.Set("x-user-agent", "connect-es/2.1.1")
	req.Header.Set("Origin", "https://grok.com")
	req.Header.Set("Referer", "https://grok.com/?_s=usage")

	resp, err := p.client.Do(req)
	if err != nil {
		return 0, err
	}
	defer resp.Body.Close()
	body, err := io.ReadAll(io.LimitReader(resp.Body, 8<<20))
	if err != nil {
		return 0, fmt.Errorf("读取 xAI quota 响应失败: %w", err)
	}
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return 0, fmt.Errorf("xAI quota HTTP %d", resp.StatusCode)
	}
	return parseXAIQuota(body)
}

// parseXAIQuota extracts the used percentage from the current GrokBuild
// protobuf shape and returns the remaining percentage, matching balance-alert's
// quota convention. It intentionally accepts only the known field path rather
// than guessing from arbitrary floats in a response.
func parseXAIQuota(body []byte) (float64, error) {
	frames, trailers, err := grpcWebFrames(body)
	if err != nil {
		return 0, err
	}
	if status := grpcStatus(trailers); status != "" && status != "0" {
		return 0, fmt.Errorf("xAI quota grpc-status %s", status)
	}

	var used *float64
	walkProto(frames, nil, func(path []int, wire byte, value uint64) {
		if wire != 5 || len(path) != 2 || path[0] != 1 || path[1] != 1 || used != nil {
			return
		}
		percent := float64(math.Float32frombits(uint32(value)))
		if percent >= 0 && percent <= 100 {
			used = &percent
		}
	})
	if used == nil {
		return 0, errors.New("xAI quota response did not contain the expected usage percentage")
	}
	remaining := 100 - *used
	if remaining < 0 {
		remaining = 0
	}
	return round2(remaining), nil
}

func grpcWebFrames(body []byte) ([]byte, string, error) {
	var data []byte
	var trailers strings.Builder
	for offset := 0; offset+5 <= len(body); {
		flags := body[offset]
		length := int(binary.BigEndian.Uint32(body[offset+1 : offset+5]))
		offset += 5
		if length < 0 || offset+length > len(body) {
			return nil, "", errors.New("invalid xAI gRPC-Web frame length")
		}
		frame := body[offset : offset+length]
		offset += length
		if flags&0x80 != 0 {
			trailers.Write(frame)
		} else {
			data = append(data, frame...)
		}
	}
	if len(data) == 0 {
		return nil, trailers.String(), errors.New("xAI quota response had no data frame")
	}
	return data, trailers.String(), nil
}

func grpcStatus(trailers string) string {
	for _, line := range strings.Split(trailers, "\n") {
		key, value, ok := strings.Cut(strings.TrimSpace(line), ":")
		if ok && strings.EqualFold(strings.TrimSpace(key), "grpc-status") {
			return strings.TrimSpace(value)
		}
	}
	return ""
}

// walkProto visits protobuf scalar fields recursively. The response is an
// implementation detail, so unknown fields and malformed nested values are
// ignored; parseXAIQuota still fails closed unless the exact usage path exists.
func walkProto(data []byte, path []int, visit func([]int, byte, uint64)) {
	for offset := 0; offset < len(data); {
		key, next, ok := readVarint(data, offset)
		if !ok || key == 0 {
			return
		}
		offset = next
		field := int(key >> 3)
		wire := byte(key & 7)
		fieldPath := append(append([]int(nil), path...), field)
		switch wire {
		case 0:
			value, next, ok := readVarint(data, offset)
			if !ok {
				return
			}
			visit(fieldPath, wire, value)
			offset = next
		case 1:
			if offset+8 > len(data) {
				return
			}
			offset += 8
		case 2:
			length, next, ok := readVarint(data, offset)
			if !ok || length > uint64(len(data)-next) {
				return
			}
			end := next + int(length)
			walkProto(data[next:end], fieldPath, visit)
			offset = end
		case 5:
			if offset+4 > len(data) {
				return
			}
			visit(fieldPath, wire, uint64(binary.LittleEndian.Uint32(data[offset:offset+4])))
			offset += 4
		default:
			return
		}
	}
}

func readVarint(data []byte, offset int) (uint64, int, bool) {
	var value uint64
	for shift := uint(0); offset < len(data) && shift < 64; shift += 7 {
		part := data[offset]
		offset++
		value |= uint64(part&0x7f) << shift
		if part&0x80 == 0 {
			return value, offset, true
		}
	}
	return 0, offset, false
}
