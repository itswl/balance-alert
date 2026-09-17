package provider

import (
	"context"
	"regexp"
	"strings"
	"testing"
	"time"
)

// 签名串必须与阿里云文档规定的算法逐字节一致，这里用固定的密钥、时刻和随机数把结果钉死，
// 防止改坏——线上签错的表现只是一个 403，不看这几条测试很难定位到是哪一步算歪了。
const (
	aliyunTestID     = "LTAI5tTestAccessKey"
	aliyunTestSecret = "testAccessKeySecret"
	aliyunTestNonce  = "f81d4fae-7dec-11d0-a765-00a0c91e6bf6"
)

var aliyunTestTime = time.Date(2024, 5, 17, 8, 30, 45, 0, time.UTC)

func aliyunProviderAt(rawURL string) *aliyunProvider {
	return &aliyunProvider{
		accessKeyID: aliyunTestID, accessKeySecret: aliyunTestSecret,
		client:  NewClient(2 * time.Second),
		baseURL: rawURL,
		now:     func() time.Time { return aliyunTestTime },
		nonce:   func() string { return aliyunTestNonce },
	}
}

func TestAliyunSignature(t *testing.T) {
	params := aliyunProviderAt(aliyunBaseURL).buildParams(aliyunTestTime, aliyunTestNonce)

	want := map[string]string{
		"Action":           "QueryAccountBalance",
		"Version":          "2017-12-14",
		"AccessKeyId":      aliyunTestID,
		"SignatureMethod":  "HMAC-SHA1",
		"SignatureVersion": "1.0",
		"SignatureNonce":   aliyunTestNonce,
		"Format":           "JSON",
		"Timestamp":        "2024-05-17T08:30:45Z",
		"Signature":        "z8MVrPhYnXWKscZGXgj/jOnJNi4=",
	}
	if len(params) != len(want) {
		t.Fatalf("参数 = %v", params)
	}
	for key, value := range want {
		if params[key] != value {
			t.Errorf("%s = %q，期望 %q", key, params[key], value)
		}
	}
}

func TestAliyunSignatureUsesUTC(t *testing.T) {
	// Timestamp 必须是 UTC，带本地时区会被判时间偏差过大
	shanghai := time.FixedZone("CST", 8*3600)
	params := aliyunProviderAt(aliyunBaseURL).buildParams(aliyunTestTime.In(shanghai), aliyunTestNonce)
	if params["Timestamp"] != "2024-05-17T08:30:45Z" {
		t.Fatalf("Timestamp = %q", params["Timestamp"])
	}
	if params["Signature"] != "z8MVrPhYnXWKscZGXgj/jOnJNi4=" {
		t.Fatalf("Signature = %q", params["Signature"])
	}
}

func TestPercentEncode(t *testing.T) {
	// RFC 3986 的编码规则，签名要求的就是这一套：空格是 %20 不是 +，* 要编码，~ 不编码
	got := percentEncode("a b+c*d~e/f=g&h%i中")
	if want := "a%20b%2Bc%2Ad~e%2Ff%3Dg%26h%25i%E4%B8%AD"; got != want {
		t.Fatalf("percentEncode\n = %q\n期望 %q", got, want)
	}
}

func TestAliyunFetch(t *testing.T) {
	cases := []struct {
		name   string
		status int
		body   string
		want   float64
		errMsg string
	}{
		{
			name: "标准结构，金额带千位分隔符",
			body: `{"Code":"Success","Message":"Successful!","RequestId":"x",
				"Data":{"AvailableAmount":"1,234.56","Currency":"CNY","AvailableCashAmount":"1,000.00"}}`,
			want: 1234.56,
		},
		{
			name: "数字状态码也算成功",
			body: `{"Code":200,"Data":{"AvailableAmount":"88.00"}}`,
			want: 88,
		},
		{
			name: "旧结构：金额在顶层",
			body: `{"AvailableAmount":"50.00"}`,
			want: 50,
		},
		{
			name: "退回 AvailableCashAmount",
			body: `{"Code":"Success","Data":{"Currency":"CNY","AvailableCashAmount":"9.90"}}`,
			want: 9.9,
		},
		{
			name: "Data.AvailableAmount 优先于顶层字段",
			body: `{"Data":{"AvailableAmount":"1.00"},"AvailableCashAmount":"999.00"}`,
			want: 1,
		},
		{
			// 阿里云的业务错误是 4xx 带 JSON 体，按状态码提前失败就会把这句话丢掉
			name:   "密钥无效（HTTP 400 带业务错误）",
			status: 400,
			body: `{"Code":"InvalidAccessKeyId.NotFound","Message":"Specified access key is not found.",
				"RequestId":"x","HostId":"business.aliyuncs.com"}`,
			errMsg: "API 返回错误: Specified access key is not found. (Code: InvalidAccessKeyId.NotFound)",
		},
		{
			name:   "业务错误缺 Message",
			body:   `{"Code":"Forbidden"}`,
			errMsg: "API 返回错误: 未知错误 (Code: Forbidden)",
		},
		{
			name:   "解析不出余额",
			body:   `{"Code":"Success","Data":{"Currency":"CNY"}}`,
			errMsg: "无法从响应中解析余额字段，响应内容: ",
		},
		{
			// Data 不是对象时也要走正常的中文提示，不能把类型断言失败漏给用户
			name:   "Data 不是对象",
			body:   `{"Code":"Success","Data":"oops"}`,
			errMsg: "无法从响应中解析余额字段，响应内容: ",
		},
		{
			name:   "空响应体",
			body:   "",
			errMsg: "API 返回空响应",
		},
		{
			name:   "不是 JSON",
			body:   `<html>502</html>`,
			errMsg: "响应内容不是有效的JSON格式：<html>502</html>",
		},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			srv, _ := serveJSON(t, tc.status, tc.body)
			got, err := aliyunProviderAt(srv.URL).Fetch(context.Background())
			if tc.errMsg != "" {
				if err == nil {
					t.Fatalf("期望失败，却拿到余额 %v", got)
				}
				if !strings.Contains(err.Error(), tc.errMsg) {
					t.Fatalf("错误消息 = %q，期望包含 %q", err.Error(), tc.errMsg)
				}
				return
			}
			if err != nil {
				t.Fatalf("Fetch 失败: %v", err)
			}
			assertFloat(t, got, tc.want)
		})
	}
}

func TestAliyunRequestIsSignedOverWhatItSends(t *testing.T) {
	srv, rec := serveJSON(t, 200, `{"Code":"Success","Data":{"AvailableAmount":"1.00"}}`)
	provider := aliyunProviderAt(srv.URL)
	if _, err := provider.Fetch(context.Background()); err != nil {
		t.Fatal(err)
	}

	// 用服务端真收到的参数重算一遍签名：签的和发的必须是同一份，
	// 少发一个参数或多发一个都会让阿里云算出不同的签名
	sent := map[string]string{}
	for key := range rec.query {
		sent[key] = rec.query.Get(key)
	}
	signature := sent["Signature"]
	if signature == "" {
		t.Fatal("请求里没有 Signature")
	}
	delete(sent, "Signature")

	if want := provider.sign(sent); want != signature {
		t.Fatalf("请求带的签名 = %q，按收到的参数重算 = %q", signature, want)
	}
	if sent["Action"] != aliyunAction || sent["Version"] != aliyunVersion {
		t.Errorf("参数 = %v", sent)
	}
}

func TestAliyunNonceIsRandomUUID(t *testing.T) {
	// SignatureNonce 重复会被当成重放攻击拒掉
	pattern := regexp.MustCompile(`^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$`)
	first, second := aliyunNonce(), aliyunNonce()
	if !pattern.MatchString(first) {
		t.Fatalf("nonce = %q，不是 v4 UUID", first)
	}
	if first == second {
		t.Fatal("两次生成的 nonce 相同")
	}
}

func TestAliyunKeyFormat(t *testing.T) {
	if _, err := New("aliyun", "LTAI5tonly-id", nil); err == nil ||
		!strings.Contains(err.Error(), "阿里云 API Key 格式错误，应为 'AccessKeyId:AccessKeySecret' 格式") {
		t.Fatalf("错误 = %v", err)
	}
	if _, err := New("aliyun", "id:secret", nil); err != nil {
		t.Fatalf("合法密钥被拒: %v", err)
	}
}
