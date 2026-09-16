// Package provider 是各平台余额查询的适配层。
//
// 绝大多数平台都是"GET 一次、从 JSON 里取个数"，这类用 Spec 声明式接入，
// 几行就能加一个新平台；需要签名的（火山、阿里云）自己实现 Provider 接口。
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

// DefaultTimeout 单次请求的超时；重试由 Client 负责。
const DefaultTimeout = 15 * time.Second

// MaxRetries 是失败后的重试次数，与 Python 版 urllib3 Retry(total=3) 对齐。
const MaxRetries = 3

// Provider 查询一个账户的当前余额。
type Provider interface {
	// Fetch 返回当前余额。语义由平台决定：货币金额、点数或剩余百分比。
	Fetch(ctx context.Context) (float64, error)
}

// Factory 用 API Key 造一个适配器。Key 格式不对时返回错误。
type Factory func(apiKey string, client *Client) (Provider, error)

// Info 是注册表里一个平台的元信息，供 /api/providers 和页面下拉框使用。
type Info struct {
	Key         string `json:"value"`
	Name        string `json:"label"`
	DefaultType string `json:"default_type"`
}

var registry = map[string]struct {
	info    Info
	factory Factory
}{}

// Register 登记一个平台。在各适配器的 init 里调用。
func Register(key, name, defaultType string, factory Factory) {
	registry[key] = struct {
		info    Info
		factory Factory
	}{Info{Key: key, Name: name, DefaultType: defaultType}, factory}
}

// New 按平台名创建适配器。
func New(key, apiKey string, client *Client) (Provider, error) {
	entry, ok := registry[key]
	if !ok {
		return nil, fmt.Errorf("未知的服务商: %s. 支持的服务商: %s", key, strings.Join(Keys(), ", "))
	}
	if client == nil {
		client = NewClient(DefaultTimeout)
	}
	return entry.factory(apiKey, client)
}

// Keys 返回所有已注册平台名，按字典序。
func Keys() []string {
	keys := make([]string, 0, len(registry))
	for k := range registry {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	return keys
}

// All 返回所有平台的元信息，按平台名排序。
func All() []Info {
	out := make([]Info, 0, len(registry))
	for _, k := range Keys() {
		out = append(out, registry[k].info)
	}
	return out
}

// Lookup 返回一个平台的元信息。
func Lookup(key string) (Info, bool) {
	entry, ok := registry[key]
	return entry.info, ok
}

// DisplayName 返回平台展示名，未注册时原样返回。
func DisplayName(key string) string {
	if info, ok := Lookup(key); ok {
		return info.Name
	}
	return key
}

// ---------- HTTP ----------

// Client 是带重试的 HTTP 客户端。适配器之间共享，连接池才有意义。
type Client struct {
	http *http.Client
}

// NewClient 创建一个带超时的客户端。
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

// 这些状态码重试一次可能就好了。
var retriableStatus = map[int]bool{429: true, 500: true, 502: true, 503: true, 504: true}

// Do 发送请求，对可重试的状态码与网络错误退避重试。
// 只对幂等方法重试，与 Python 版 allowed_methods 一致。
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
		// 丢弃响应体才能复用连接
		_, _ = io.Copy(io.Discard, io.LimitReader(resp.Body, 4<<10))
		resp.Body.Close()
		lastErr = fmt.Errorf("HTTP %d", resp.StatusCode)
	}
	return nil, classify(lastErr)
}

// GetJSON 发一个 GET 并把响应解析成 map。
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
		return nil, fmt.Errorf("读取响应失败: %w", err)
	}
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("HTTP %d: %s", resp.StatusCode, http.StatusText(resp.StatusCode))
	}

	var data map[string]any
	if err := json.Unmarshal(body, &data); err != nil {
		return nil, errors.New("响应不是有效的 JSON 格式")
	}
	return data, nil
}

// classify 把底层网络错误翻译成给用户看的消息，与 Python 版 _classify_exception 对齐。
func classify(err error) error {
	if err == nil {
		return nil
	}
	var netErr interface{ Timeout() bool }
	if errors.As(err, &netErr) && netErr.Timeout() {
		return errors.New("请求超时")
	}
	if errors.Is(err, context.DeadlineExceeded) {
		return errors.New("请求超时")
	}
	if strings.HasPrefix(err.Error(), "HTTP ") {
		return err
	}
	return fmt.Errorf("网络连接错误: %w", err)
}

// ---------- 声明式适配器 ----------

// AuthMode 决定 API Key 放在哪。
type AuthMode int

const (
	AuthBearer AuthMode = iota // Authorization: Bearer <key>
	AuthQuery                  // 拼进查询参数
)

// Spec 声明一个"GET 一次、从 JSON 里取个数"的余额接口。
type Spec struct {
	Key         string // 注册名，如 deepseek
	Name        string // 展示名，如 DeepSeek
	DefaultType string // 余额类型：balance / credits / quota
	URL         string
	Auth        AuthMode
	AuthParam   string // Auth 为 AuthQuery 时的参数名
	Headers     map[string]string
	Params      map[string]string

	// Check 做业务层成功校验，返回错误表示这次查询失败。可空。
	Check func(data map[string]any) error
	// Extract 从响应里取余额，取不到就返回错误。
	Extract func(data map[string]any) (float64, error)
}

// RegisterSpec 用声明式 Spec 注册一个平台。
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

// ---------- JSON 取值助手 ----------

// Dig 按路径取嵌套字段，任一层不是对象就返回 nil。
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

// Object 把值断言成对象，失败返回 nil。
func Object(v any) map[string]any {
	obj, _ := v.(map[string]any)
	return obj
}

// Num 把 JSON 里的数值（可能是 float64 或带千位分隔符的字符串）转成 float64。
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

// Str 把值当字符串取，非字符串返回空。
func Str(v any) string {
	s, _ := v.(string)
	return s
}

// ---------- 日志脱敏 ----------

var sensitiveQueryKeys = map[string]bool{
	"access_token": true, "ak": true, "api_key": true, "authorization": true,
	"key": true, "secret": true, "signature": true, "sk": true, "token": true,
}

// MaskURL 把 URL 里的密钥与 webhook token 打码，用于日志。
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
			// String() 默认会把 * 转义成 %2A，日志里的 abcd%2A%2A%2A7890 没法看；
			// RawPath 指定原样输出，与 Python 版打出来的一致
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

// SplitKeyPair 拆开 "ID:Secret" 形式的密钥，火山与阿里云用。
// label 是平台名，format 是这个平台的密钥写法（如 "AK:SK"），两者拼成给用户看的提示。
func SplitKeyPair(apiKey, label, format string) (string, string, error) {
	id, secret, ok := strings.Cut(apiKey, ":")
	if !ok || id == "" || secret == "" {
		return "", "", fmt.Errorf("%s API Key 格式错误，应为 '%s' 格式", label, format)
	}
	return id, secret, nil
}
