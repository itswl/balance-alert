package provider

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strconv"
	"strings"
)

// Implementation note.
// Implementation note.
// Implementation note.

// Implementation note.
// Implementation note.
// Implementation note.
func truthy(v any) bool {
	switch value := v.(type) {
	case nil:
		return false
	case bool:
		return value
	case float64:
		return value != 0
	case int:
		return value != 0
	case json.Number:
		f, err := value.Float64()
		return err == nil && f != 0
	case string:
		return value != ""
	case []any:
		return len(value) > 0
	case map[string]any:
		return len(value) > 0
	}
	return true
}

// Implementation note.
//
// Implementation note.
// Implementation note.
// Implementation note.
func jsonNum(v any) (float64, bool) {
	switch value := v.(type) {
	case float64:
		return value, true
	case int:
		return float64(value), true
	case json.Number:
		f, err := value.Float64()
		return f, err == nil
	}
	return 0, false
}

// Implementation note.
// Implementation note.
func orElse(a, b any) any {
	if truthy(a) {
		return a
	}
	return b
}

// Implementation note.
// Implementation note.
func messageOr(data map[string]any, key, fallback string) string {
	value, ok := data[key]
	if !ok {
		return fallback
	}
	return formatValue(value)
}

// Implementation note.
// Implementation note.
// Implementation note.
func formatValue(v any) string {
	switch value := v.(type) {
	case string:
		return value
	case float64:
		return strconv.FormatFloat(value, 'f', -1, 64)
	case int:
		return strconv.Itoa(value)
	}
	var buf bytes.Buffer
	enc := json.NewEncoder(&buf)
	enc.SetEscapeHTML(false) // operation,operation & < > operation & operation
	if err := enc.Encode(v); err != nil {
		return fmt.Sprint(v)
	}
	return strings.TrimRight(buf.String(), "\n")
}

// Implementation note.
// Implementation note.
func round2(v float64) float64 {
	rounded, err := strconv.ParseFloat(strconv.FormatFloat(v, 'f', 2, 64), 64)
	if err != nil {
		return v
	}
	return rounded
}

// Implementation note.
// Implementation note.
// Implementation note.
func percentEncode(s string) string {
	var b strings.Builder
	b.Grow(len(s))
	for i := 0; i < len(s); i++ {
		c := s[i]
		switch {
		case 'a' <= c && c <= 'z', 'A' <= c && c <= 'Z', '0' <= c && c <= '9',
			c == '-', c == '_', c == '.', c == '~':
			b.WriteByte(c)
		default:
			fmt.Fprintf(&b, "%%%02X", c)
		}
	}
	return b.String()
}

// Implementation note.
// Implementation note.
// Implementation note.
func fetchBody(client *Client, req *http.Request) (int, string, error) {
	resp, err := client.Do(req)
	if err != nil {
		return 0, "", err
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(io.LimitReader(resp.Body, 4<<20))
	if err != nil {
		return resp.StatusCode, "", fmt.Errorf("failed to read response: %w", err)
	}
	return resp.StatusCode, string(body), nil
}

// Implementation note.
// Implementation note.
func parseJSONObject(body string) (map[string]any, error) {
	if strings.TrimSpace(body) == "" {
		return nil, nil
	}
	var data map[string]any
	if err := json.Unmarshal([]byte(body), &data); err != nil {
		return nil, fmt.Errorf("Response is not valid JSON:%s", body)
	}
	return data, nil
}
