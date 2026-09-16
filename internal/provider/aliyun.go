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

// 阿里云查的是账户可用额度（人民币）。
// 签名是老的 RPC 风格：把参数排序拼成规范串，再用 HMAC-SHA1 签名。
// 算法是接口规定的，不是我们选的——新接口才用 V3/HMAC-SHA256。
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
	// now 与 nonce 可替换，测试才能固定签名结果
	now   func() time.Time
	nonce func() string
}

func init() {
	Register("aliyun", "阿里云", "balance", func(apiKey string, client *Client) (Provider, error) {
		id, secret, err := SplitKeyPair(apiKey, "阿里云", "AccessKeyId:AccessKeySecret")
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
		return 0, errors.New("API 返回空响应")
	}
	return aliyunExtractAmount(data)
}

// aliyunExtractAmount 解析余额。阿里云不同版本接口的返回结构不一，
// 带 Code 的标准结构和直接给余额字段的旧结构都要认。
func aliyunExtractAmount(data map[string]any) (float64, error) {
	if code, ok := data["Code"]; ok && code != nil && !aliyunCodeOK(code) {
		return 0, fmt.Errorf("API 返回错误: %s (Code: %s)",
			messageOr(data, "Message", "未知错误"), formatValue(code))
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
		// 金额可能是带千位分隔符的字符串（"1,234.56"），Num 已经处理了逗号
		if amount, ok := Num(candidate); ok {
			return amount, nil
		}
		break
	}
	return 0, fmt.Errorf("无法从响应中解析余额字段，响应内容: %s", formatValue(data))
}

// aliyunCodeOK 判业务状态码：字符串 "Success"、数字 200、字符串 "200" 都算成功。
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

	// 状态码故意不判：阿里云的业务错误就是 4xx + JSON 体，
	// 按状态码提前失败会把 "AccessKey 无效" 这类有用信息换成一句 HTTP 400
	_, body, err := fetchBody(p.client, req)
	if err != nil {
		return nil, err
	}
	return parseJSONObject(body)
}

// buildParams 拼出带签名的完整请求参数。
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

// sign 计算 RPC 签名：规范化查询串 -> 待签名串 -> HMAC-SHA1 -> base64。
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

	// 待签名串把整个查询串再编码一次，"/" 也要编码成 %2F
	stringToSign := "GET&" + percentEncode("/") + "&" + percentEncode(canonicalQuery)

	// 密钥末尾那个 & 是阿里云规定的，不是拼错
	mac := hmac.New(sha1.New, []byte(p.accessKeySecret+"&"))
	mac.Write([]byte(stringToSign))
	return base64.StdEncoding.EncodeToString(mac.Sum(nil))
}

// aliyunNonce 生成 v4 UUID 当 SignatureNonce。阿里云只要求它别重复（防重放），
// 标准库就能满足，不值得为此多一个依赖。
func aliyunNonce() string {
	var b [16]byte
	// crypto/rand.Read 不会失败，失败它自己会 panic
	_, _ = rand.Read(b[:])
	b[6] = (b[6] & 0x0f) | 0x40 // 版本 4
	b[8] = (b[8] & 0x3f) | 0x80 // RFC 4122 variant
	return fmt.Sprintf("%x-%x-%x-%x-%x", b[0:4], b[4:6], b[6:8], b[8:10], b[10:16])
}
