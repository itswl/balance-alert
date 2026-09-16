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

// 火山云查的是账户可用余额（人民币）。
// 签名算法是火山引擎 V4（HMAC-SHA256），与 AWS SigV4 同构：
// 先把请求规范化成固定格式，再用「日期/地域/服务/request」四级派生出的密钥签名。
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

// volcSignedHeaders 是参与签名的请求头，顺序即签名顺序。
// 规范请求里的头列表和 Authorization 里的 SignedHeaders 必须一致，所以只定义这一处。
var volcSignedHeaders = []string{"content-type", "host", "x-content-sha256", "x-date"}

type volcProvider struct {
	ak, sk  string
	client  *Client
	baseURL string
	// now 单独拎出来是为了测试能固定时间——签名结果随时间变，否则没法断言
	now func() time.Time
}

func init() {
	Register("volc", "火山云", "balance", func(apiKey string, client *Client) (Provider, error) {
		ak, sk, err := SplitKeyPair(apiKey, "火山云", "AK:SK")
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
		return 0, errors.New("API 返回空响应")
	}

	// 火山把业务错误塞在 ResponseMetadata.Error 里，HTTP 状态码仍然可能是 200
	if info := Dig(data, "ResponseMetadata", "Error"); truthy(info) {
		return 0, fmt.Errorf("API 返回错误: %s", formatValue(info))
	}

	balance, ok := Num(Dig(data, "Result", "AvailableBalance"))
	if !ok {
		return 0, errors.New("无法从响应中解析 AvailableBalance 字段")
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
			// host 参与了签名，请求头里的 Host 必须与签名时一致；
			// Go 不让通过 Header 设置 Host，只能写 req.Host
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
		return nil, fmt.Errorf("HTTP请求失败，状态码：%d\n响应内容：%s", status, body)
	}
	return parseJSONObject(body)
}

func (p *volcProvider) query() map[string]string {
	return map[string]string{"Action": volcAction, "Version": volcVersion}
}

// buildHeaders 构建带签名的请求头。body 是请求体原文，GET 查询时是空串。
func (p *volcProvider) buildHeaders(now time.Time, body string) map[string]string {
	xDate := now.UTC().Format("20060102T150405Z")
	shortDate := xDate[:8]
	contentSHA256 := volcSHA256(body)
	credentialScope := strings.Join([]string{shortDate, volcRegion, volcService, "request"}, "/")
	signedHeaders := strings.Join(volcSignedHeaders, ";")

	// 规范请求：方法 / 路径 / 查询串 / 头 / 空行 / 签名头列表 / body 摘要
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

	// 派生签名密钥：从 SK 出发，按日期、地域、服务、request 逐级 HMAC，
	// 这样泄露某一级的中间密钥也只影响那一天那个服务
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

// volcNormQuery 规范化查询参数：键排序、RFC 3986 编码，签名和真实请求用的是同一串。
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
