// Package provider provides the package implementation.
//
// Implementation note.
// Implementation note.
package provider

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"math"
	"net/http"
	"net/url"
	"sort"
	"strconv"
	"strings"
	"time"
)

// Implementation note.
const DefaultTimeout = 15 * time.Second

// Implementation note.
const MaxRetries = 3

// Implementation note.
type Provider interface {
	// Implementation note.
	Fetch(ctx context.Context) (float64, error)
}

// Implementation note.
type Factory func(apiKey string, client *Client) (Provider, error)

// Implementation note.
type Info struct {
	Key         string `json:"value"`
	Name        string `json:"label"`
	DefaultType string `json:"default_type"`
}

var registry = map[string]struct {
	info    Info
	factory Factory
}{}

// Implementation note.
func Register(key, name, defaultType string, factory Factory) {
	registry[key] = struct {
		info    Info
		factory Factory
	}{Info{Key: key, Name: name, DefaultType: defaultType}, factory}
}

// Implementation note.
func New(key, apiKey string, client *Client) (Provider, error) {
	entry, ok := registry[key]
	if !ok {
		return nil, fmt.Errorf("Unknown provider: %s. Supported providers: %s", key, strings.Join(Keys(), ", "))
	}
	if client == nil {
		client = NewClient(DefaultTimeout)
	}
	return entry.factory(apiKey, client)
}

// Implementation note.
func Keys() []string {
	keys := make([]string, 0, len(registry))
	for k := range registry {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	return keys
}

// Implementation note.
func All() []Info {
	out := make([]Info, 0, len(registry))
	for _, k := range Keys() {
		out = append(out, registry[k].info)
	}
	return out
}

// Implementation note.
func Lookup(key string) (Info, bool) {
	entry, ok := registry[key]
	return entry.info, ok
}

// Implementation note.
func DisplayName(key string) string {
	if info, ok := Lookup(key); ok {
		return info.Name
	}
	return key
}

// ---------- HTTP ----------

// Implementation note.
type Client struct {
	http *http.Client
}

// Implementation note.
func NewClient(timeout time.Duration) *Client {
	if timeout <= 0 {
		timeout = DefaultTimeout
	}
	return &Client{http: &http.Client{
		Timeout: timeout,
		Transport: &http.Transport{
			MaxIdleConns:        64,
			MaxIdleConnsPerHost: 8,
			IdleConnTimeout:     90 * time.Second,
		},
	}}
}

// Implementation note.
var retriableStatus = map[int]bool{429: true, 500: true, 502: true, 503: true, 504: true}

// Implementation note.
// Implementation note.
func (c *Client) Do(req *http.Request) (*http.Response, error) {
	idempotent := req.Method == http.MethodGet || req.Method == http.MethodHead || req.Method == http.MethodOptions

	var lastErr error
	for attempt := 0; attempt <= MaxRetries; attempt++ {
		if attempt > 0 {
			wait := time.Duration(float64(time.Second) * 0.5 * math.Pow(2, float64(attempt-1)))
			select {
			case <-req.Context().Done():
				return nil, req.Context().Err()
			case <-time.After(wait):
			}
		}

		resp, err := c.http.Do(req.Clone(req.Context()))
		if err != nil {
			lastErr = err
			if !idempotent || req.Context().Err() != nil {
				break
			}
			continue
		}
		if !idempotent || !retriableStatus[resp.StatusCode] || attempt == MaxRetries {
			return resp, nil
		}
		// Implementation note.
		_, _ = io.Copy(io.Discard, io.LimitReader(resp.Body, 4<<10))
		resp.Body.Close()
		lastErr = fmt.Errorf("HTTP %d", resp.StatusCode)
	}
	return nil, classify(lastErr)
}

// Implementation note.
func (c *Client) GetJSON(ctx context.Context, rawURL string, headers map[string]string, params map[string]string) (map[string]any, error) {
	if len(params) > 0 {
		q := url.Values{}
		for k, v := range params {
			q.Set(k, v)
		}
		if strings.Contains(rawURL, "?") {
			rawURL += "&" + q.Encode()
		} else {
			rawURL += "?" + q.Encode()
		}
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, rawURL, nil)
	if err != nil {
		return nil, err
	}
	for k, v := range headers {
		req.Header.Set(k, v)
	}

	resp, err := c.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(io.LimitReader(resp.Body, 4<<20))
	if err != nil {
		return nil, fmt.Errorf("failed to read provider response: %w", err)
	}
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("HTTP %d: %s", resp.StatusCode, http.StatusText(resp.StatusCode))
	}

	var data map[string]any
	if err := json.Unmarshal(body, &data); err != nil {
		return nil, errors.New("Response is not valid JSON")
	}
	return data, nil
}

// Implementation note.
// Implementation note.
func classify(err error) error {
	if err == nil {
		return nil
	}
	var netErr interface{ Timeout() bool }
	if errors.As(err, &netErr) && netErr.Timeout() {
		return errors.New("Request timed out")
	}
	if errors.Is(err, context.DeadlineExceeded) {
		return errors.New("Request timed out")
	}
	if strings.HasPrefix(err.Error(), "HTTP ") {
		return err
	}
	return fmt.Errorf("Network connection error: %w", err)
}

// Implementation note.

// Implementation note.
type AuthMode int

const (
	AuthBearer AuthMode = iota // Authorization: Bearer <key>
	AuthQuery                  // operation
)

// Implementation note.
type Spec struct {
	Key         string // operation,operation deepseek
	Name        string // operation,operation DeepSeek
	DefaultType string // operation:balance / credits / quota
	URL         string
	Auth        AuthMode
	AuthParam   string // Auth operation AuthQuery operation
	Headers     map[string]string
	Params      map[string]string

	// Implementation note.
	Check func(data map[string]any) error
	// Implementation note.
	Extract func(data map[string]any) (float64, error)
}

// Implementation note.
func RegisterSpec(spec Spec) {
	Register(spec.Key, spec.Name, spec.DefaultType, func(apiKey string, client *Client) (Provider, error) {
		return &specProvider{spec: spec, apiKey: apiKey, client: client}, nil
	})
}

type specProvider struct {
	spec   Spec
	apiKey string
	client *Client
}

func (p *specProvider) Fetch(ctx context.Context) (float64, error) {
	headers := make(map[string]string, len(p.spec.Headers)+1)
	for k, v := range p.spec.Headers {
		headers[k] = v
	}
	params := make(map[string]string, len(p.spec.Params)+1)
	for k, v := range p.spec.Params {
		params[k] = v
	}
	if p.spec.Auth == AuthBearer {
		headers["Authorization"] = "Bearer " + p.apiKey
	} else {
		params[p.spec.AuthParam] = p.apiKey
	}

	data, err := p.client.GetJSON(ctx, p.spec.URL, headers, params)
	if err != nil {
		return 0, err
	}
	if p.spec.Check != nil {
		if err := p.spec.Check(data); err != nil {
			return 0, err
		}
	}
	return p.spec.Extract(data)
}

// Implementation note.

// Implementation note.
func Dig(data map[string]any, path ...string) any {
	var current any = data
	for _, key := range path {
		obj, ok := current.(map[string]any)
		if !ok {
			return nil
		}
		current = obj[key]
	}
	return current
}

// Implementation note.
func Object(v any) map[string]any {
	obj, _ := v.(map[string]any)
	return obj
}

// Implementation note.
func Num(v any) (float64, bool) {
	switch value := v.(type) {
	case float64:
		return value, true
	case json.Number:
		f, err := value.Float64()
		return f, err == nil
	case string:
		f, err := strconv.ParseFloat(strings.ReplaceAll(strings.TrimSpace(value), ",", ""), 64)
		return f, err == nil
	case int:
		return float64(value), true
	case bool:
		return 0, false
	}
	return 0, false
}

// Implementation note.
func Str(v any) string {
	s, _ := v.(string)
	return s
}

// Implementation note.

var sensitiveQueryKeys = map[string]bool{
	"access_token": true, "ak": true, "api_key": true, "authorization": true,
	"key": true, "secret": true, "signature": true, "sk": true, "token": true,
}

// Implementation note.
func MaskURL(raw string) string {
	parsed, err := url.Parse(raw)
	if err != nil {
		return raw
	}
	for _, marker := range []string{"/hook/", "/token/", "/access_token/"} {
		idx := strings.Index(parsed.Path, marker)
		if idx < 0 {
			continue
		}
		prefix := parsed.Path[:idx+len(marker)]
		rest := parsed.Path[idx+len(marker):]
		token, tail, hasTail := strings.Cut(rest, "/")
		if token != "" {
			masked := "***"
			if len(token) > 8 {
				masked = token[:4] + "***" + token[len(token)-4:]
			}
			parsed.Path = prefix + masked
			if hasTail {
				parsed.Path += "/" + tail
			}
			// Implementation note.
			// Implementation note.
			parsed.RawPath = parsed.Path
		}
		break
	}

	query := parsed.Query()
	for key, values := range query {
		if !sensitiveQueryKeys[strings.ToLower(key)] {
			continue
		}
		for i, v := range values {
			if v == "" {
				continue
			}
			if len(v) > 8 {
				values[i] = v[:4] + "***" + v[len(v)-4:]
			} else {
				values[i] = "***"
			}
		}
		query[key] = values
	}
	parsed.RawQuery = query.Encode()
	return parsed.String()
}

// Implementation note.
// Implementation note.
func SplitKeyPair(apiKey, label, format string) (string, string, error) {
	id, secret, ok := strings.Cut(apiKey, ":")
	if !ok || id == "" || secret == "" {
		return "", "", fmt.Errorf("%s: invalid API key format; expected '%s'", label, format)
	}
	return id, secret, nil
}
