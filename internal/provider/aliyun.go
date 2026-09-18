package provider

import (
	"context"
	"crypto/hmac"
	"crypto/rand"
	"crypto/sha1"
	"encoding/base64"
	"errors"
	"fmt"
	"net/http"
	"net/url"
	"sort"
	"strings"
	"time"
)

// Implementation note.
// Implementation note.
// Implementation note.
const (
	aliyunEndpoint = "business.aliyuncs.com"
	aliyunAction   = "QueryAccountBalance"
	aliyunVersion  = "2017-12-14"
	aliyunBaseURL  = "https://" + aliyunEndpoint
)

type aliyunProvider struct {
	accessKeyID     string
	accessKeySecret string
	client          *Client
	baseURL         string
	// Implementation note.
	now   func() time.Time
	nonce func() string
}

func init() {
	Register("aliyun", "Alibaba Cloud", "balance", func(apiKey string, client *Client) (Provider, error) {
		id, secret, err := SplitKeyPair(apiKey, "Alibaba Cloud", "AccessKeyId:AccessKeySecret")
		if err != nil {
			return nil, err
		}
		return &aliyunProvider{
			accessKeyID: id, accessKeySecret: secret, client: client,
			baseURL: aliyunBaseURL,
			now:     func() time.Time { return time.Now().UTC() },
			nonce:   aliyunNonce,
		}, nil
	})
}

func (p *aliyunProvider) Fetch(ctx context.Context) (float64, error) {
	data, err := p.request(ctx)
	if err != nil {
		return 0, err
	}
	if len(data) == 0 {
		return 0, errors.New("API returned an empty response")
	}
	return aliyunExtractAmount(data)
}

// Implementation note.
// Implementation note.
func aliyunExtractAmount(data map[string]any) (float64, error) {
	if code, ok := data["Code"]; ok && code != nil && !aliyunCodeOK(code) {
		return 0, fmt.Errorf("API returned an error: %s (Code: %s)",
			messageOr(data, "Message", "Unknown error"), formatValue(code))
	}

	scope := Object(data["Data"])
	candidates := []any{
		scope["AvailableAmount"],
		data["AvailableAmount"],
		data["AvailableCashAmount"],
		scope["AvailableCashAmount"],
	}
	for _, candidate := range candidates {
		if candidate == nil {
			continue
		}
		// Implementation note.
		if amount, ok := Num(candidate); ok {
			return amount, nil
		}
		break
	}
	return 0, fmt.Errorf("Could not parse balance field, response: %s", formatValue(data))
}

// Implementation note.
func aliyunCodeOK(code any) bool {
	if s, ok := code.(string); ok && s == "Success" {
		return true
	}
	if n, ok := jsonNum(code); ok && n == 200 {
		return true
	}
	return formatValue(code) == "200"
}

func (p *aliyunProvider) request(ctx context.Context) (map[string]any, error) {
	query := url.Values{}
	for key, value := range p.buildParams(p.now(), p.nonce()) {
		query.Set(key, value)
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, p.baseURL+"?"+query.Encode(), nil)
	if err != nil {
		return nil, err
	}

	// Implementation note.
	// Implementation note.
	_, body, err := fetchBody(p.client, req)
	if err != nil {
		return nil, err
	}
	return parseJSONObject(body)
}

// Implementation note.
func (p *aliyunProvider) buildParams(now time.Time, nonce string) map[string]string {
	params := map[string]string{
		"Action":           aliyunAction,
		"Version":          aliyunVersion,
		"AccessKeyId":      p.accessKeyID,
		"SignatureMethod":  "HMAC-SHA1",
		"Timestamp":        now.UTC().Format("2006-01-02T15:04:05Z"),
		"SignatureVersion": "1.0",
		"SignatureNonce":   nonce,
		"Format":           "JSON",
	}
	params["Signature"] = p.sign(params)
	return params
}

// Implementation note.
func (p *aliyunProvider) sign(params map[string]string) string {
	keys := make([]string, 0, len(params))
	for key := range params {
		keys = append(keys, key)
	}
	sort.Strings(keys)

	pairs := make([]string, 0, len(keys))
	for _, key := range keys {
		pairs = append(pairs, percentEncode(key)+"="+percentEncode(params[key]))
	}
	canonicalQuery := strings.Join(pairs, "&")

	// Implementation note.
	stringToSign := "GET&" + percentEncode("/") + "&" + percentEncode(canonicalQuery)

	// Implementation note.
	mac := hmac.New(sha1.New, []byte(p.accessKeySecret+"&"))
	mac.Write([]byte(stringToSign))
	return base64.StdEncoding.EncodeToString(mac.Sum(nil))
}

// Implementation note.
// Implementation note.
func aliyunNonce() string {
	var b [16]byte
	// Implementation note.
	_, _ = rand.Read(b[:])
	b[6] = (b[6] & 0x0f) | 0x40 // operation 4
	b[8] = (b[8] & 0x3f) | 0x80 // RFC 4122 variant
	return fmt.Sprintf("%x-%x-%x-%x-%x", b[0:4], b[4:6], b[6:8], b[8:10], b[10:16])
}
