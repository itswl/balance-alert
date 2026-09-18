package provider

import (
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"net/http"
	"sort"
	"strings"
	"time"
)

// Implementation note.
// Implementation note.
// Implementation note.
const (
	volcService     = "billing"
	volcAction      = "QueryBalanceAcct"
	volcVersion     = "2022-01-01"
	volcRegion      = "cn-shanghai"
	volcHost        = "open.volcengineapi.com"
	volcContentType = "application/json"
	volcPath        = "/"
	volcMethod      = http.MethodGet
	volcBaseURL     = "https://" + volcHost
)

// Implementation note.
// Implementation note.
var volcSignedHeaders = []string{"content-type", "host", "x-content-sha256", "x-date"}

type volcProvider struct {
	ak, sk  string
	client  *Client
	baseURL string
	// Implementation note.
	now func() time.Time
}

func init() {
	Register("volc", "Volcengine", "balance", func(apiKey string, client *Client) (Provider, error) {
		ak, sk, err := SplitKeyPair(apiKey, "Volcengine", "AK:SK")
		if err != nil {
			return nil, err
		}
		return &volcProvider{
			ak: ak, sk: sk, client: client,
			baseURL: volcBaseURL,
			now:     func() time.Time { return time.Now().UTC() },
		}, nil
	})
}

func (p *volcProvider) Fetch(ctx context.Context) (float64, error) {
	data, err := p.request(ctx)
	if err != nil {
		return 0, err
	}
	if len(data) == 0 {
		return 0, errors.New("API returned an empty response")
	}

	// Implementation note.
	if info := Dig(data, "ResponseMetadata", "Error"); truthy(info) {
		return 0, fmt.Errorf("API returned an error: %s", formatValue(info))
	}

	balance, ok := Num(Dig(data, "Result", "AvailableBalance"))
	if !ok {
		return 0, errors.New("Could not parse AvailableBalance field")
	}
	return balance, nil
}

func (p *volcProvider) request(ctx context.Context) (map[string]any, error) {
	rawURL := p.baseURL + volcPath + "?" + volcNormQuery(p.query())
	req, err := http.NewRequestWithContext(ctx, volcMethod, rawURL, nil)
	if err != nil {
		return nil, err
	}
	for name, value := range p.buildHeaders(p.now(), "") {
		if name == "Host" {
			// Implementation note.
			// Implementation note.
			req.Host = value
			continue
		}
		req.Header.Set(name, value)
	}

	status, body, err := fetchBody(p.client, req)
	if err != nil {
		return nil, err
	}
	if status != http.StatusOK {
		return nil, fmt.Errorf("HTTP request failed, status code: %d\nresponse body: %s", status, body)
	}
	return parseJSONObject(body)
}

func (p *volcProvider) query() map[string]string {
	return map[string]string{"Action": volcAction, "Version": volcVersion}
}

// Implementation note.
func (p *volcProvider) buildHeaders(now time.Time, body string) map[string]string {
	xDate := now.UTC().Format("20060102T150405Z")
	shortDate := xDate[:8]
	contentSHA256 := volcSHA256(body)
	credentialScope := strings.Join([]string{shortDate, volcRegion, volcService, "request"}, "/")
	signedHeaders := strings.Join(volcSignedHeaders, ";")

	// Implementation note.
	canonicalRequest := strings.Join([]string{
		volcMethod,
		volcPath,
		volcNormQuery(p.query()),
		"content-type:" + volcContentType,
		"host:" + volcHost,
		"x-content-sha256:" + contentSHA256,
		"x-date:" + xDate,
		"",
		signedHeaders,
		contentSHA256,
	}, "\n")

	stringToSign := strings.Join([]string{
		"HMAC-SHA256", xDate, credentialScope, volcSHA256(canonicalRequest),
	}, "\n")

	// Implementation note.
	// Implementation note.
	signingKey := []byte(p.sk)
	for _, part := range []string{shortDate, volcRegion, volcService, "request"} {
		signingKey = volcHMAC(signingKey, part)
	}
	signature := hex.EncodeToString(volcHMAC(signingKey, stringToSign))

	return map[string]string{
		"Host":             volcHost,
		"X-Content-Sha256": contentSHA256,
		"X-Date":           xDate,
		"Content-Type":     volcContentType,
		"Authorization": fmt.Sprintf(
			"HMAC-SHA256 Credential=%s/%s, SignedHeaders=%s, Signature=%s",
			p.ak, credentialScope, signedHeaders, signature,
		),
	}
}

// Implementation note.
func volcNormQuery(params map[string]string) string {
	keys := make([]string, 0, len(params))
	for key := range params {
		keys = append(keys, key)
	}
	sort.Strings(keys)

	items := make([]string, 0, len(keys))
	for _, key := range keys {
		items = append(items, percentEncode(key)+"="+percentEncode(params[key]))
	}
	return strings.Join(items, "&")
}

func volcSHA256(content string) string {
	sum := sha256.Sum256([]byte(content))
	return hex.EncodeToString(sum[:])
}

func volcHMAC(key []byte, content string) []byte {
	mac := hmac.New(sha256.New, key)
	mac.Write([]byte(content))
	return mac.Sum(nil)
}
