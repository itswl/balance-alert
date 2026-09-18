package provider

import (
	"context"
	"io"
	"math"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"sync"
	"testing"
	"time"
)

// Implementation note.

// Implementation note.
type recorded struct {
	mu      sync.Mutex
	count   int
	header  http.Header
	query   url.Values
	host    string
	method  string
	rawPath string
}

func (r *recorded) snapshot(req *http.Request) {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.count++
	r.header = req.Header.Clone()
	r.query = req.URL.Query()
	r.host = req.Host
	r.method = req.Method
	r.rawPath = req.URL.Path
}

func (r *recorded) requests() int {
	r.mu.Lock()
	defer r.mu.Unlock()
	return r.count
}

// Implementation note.
func serveJSON(t *testing.T, status int, body string) (*httptest.Server, *recorded) {
	t.Helper()
	if status == 0 {
		status = http.StatusOK
	}
	rec := &recorded{}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		rec.snapshot(req)
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(status)
		_, _ = io.WriteString(w, body)
	}))
	t.Cleanup(srv.Close)
	return srv, rec
}

// Implementation note.
// Implementation note.
func specProviderAt(spec Spec, rawURL, apiKey string) Provider {
	spec.URL = rawURL
	return &specProvider{spec: spec, apiKey: apiKey, client: NewClient(2 * time.Second)}
}

// Implementation note.
type specCase struct {
	name   string
	status int
	body   string
	want   float64
	errMsg string // 非空表示expected失败，且error message包含这段
}

func runSpecCases(t *testing.T, spec Spec, cases []specCase) {
	t.Helper()
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			srv, _ := serveJSON(t, tc.status, tc.body)
			got, err := specProviderAt(spec, srv.URL, "test-key").Fetch(context.Background())
			if tc.errMsg != "" {
				if err == nil {
					t.Fatalf("expected失败，却拿到余额 %v", got)
				}
				if !strings.Contains(err.Error(), tc.errMsg) {
					t.Fatalf("error message = %q，expected包含 %q", err.Error(), tc.errMsg)
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

func assertFloat(t *testing.T, got, want float64) {
	t.Helper()
	if math.Abs(got-want) > 1e-9 {
		t.Fatalf("余额 = %v，expected %v", got, want)
	}
}

// Implementation note.

func TestRegistry(t *testing.T) {
	// Implementation note.
	want := []Info{
		{Key: "aliyun", Name: "Alibaba Cloud", DefaultType: "balance"},
		{Key: "deepseek", Name: "DeepSeek", DefaultType: "balance"},
		{Key: "glm", Name: "GLM", DefaultType: "quota"},
		{Key: "openrouter", Name: "OpenRouter", DefaultType: "credits"},
		{Key: "tikhub", Name: "TikHub", DefaultType: "balance"},
		{Key: "uniapi", Name: "UniAPI", DefaultType: "credits"},
		{Key: "volc", Name: "Volcengine", DefaultType: "balance"},
		{Key: "wxrank", Name: "WxRank", DefaultType: "credits"},
	}
	got := All()
	if len(got) != len(want) {
		t.Fatalf("注册了 %d 个平台，expected %d 个: %v", len(got), len(want), Keys())
	}
	for i, info := range want {
		if got[i] != info {
			t.Errorf("第 %d 个平台 = %+v，expected %+v", i, got[i], info)
		}
	}
}

func TestNewUnknownProvider(t *testing.T) {
	_, err := New("nope", "key", nil)
	if err == nil || !strings.Contains(err.Error(), "Unknown provider: nope") {
		t.Fatalf("error = %v，expected提示Unknown provider", err)
	}
}

func TestDisplayName(t *testing.T) {
	if got := DisplayName("volc"); got != "Volcengine" {
		t.Errorf("DisplayName(volc) = %q", got)
	}
	// Implementation note.
	if got := DisplayName("mystery"); got != "mystery" {
		t.Errorf("DisplayName(mystery) = %q", got)
	}
}

// Implementation note.

func TestClientRetriesAfterTooManyRequests(t *testing.T) {
	var hits int
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		hits++
		if hits == 1 {
			w.WriteHeader(http.StatusTooManyRequests)
			_, _ = io.WriteString(w, `{"error":"slow down"}`)
			return
		}
		_, _ = io.WriteString(w, `{"ok":true}`)
	}))
	defer srv.Close()

	data, err := NewClient(2*time.Second).GetJSON(context.Background(), srv.URL, nil, nil)
	if err != nil {
		t.Fatalf("重试后仍失败: %v", err)
	}
	if data["ok"] != true {
		t.Fatalf("response = %v", data)
	}
	if hits != 2 {
		t.Fatalf("请求了 %d 次，expected 429 之后重试一次共 2 次", hits)
	}
}

func TestClientDoesNotRetryNonIdempotent(t *testing.T) {
	// Implementation note.
	srv, rec := serveJSON(t, http.StatusTooManyRequests, `{"error":"slow down"}`)

	req, err := http.NewRequest(http.MethodPost, srv.URL, strings.NewReader("{}"))
	if err != nil {
		t.Fatal(err)
	}
	resp, err := NewClient(2 * time.Second).Do(req)
	if err != nil {
		t.Fatalf("Do 返回error: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusTooManyRequests {
		t.Fatalf("status code = %d，expected原样返回 429", resp.StatusCode)
	}
	if n := rec.requests(); n != 1 {
		t.Fatalf("请求了 %d 次，expected POST 不重试只发 1 次", n)
	}
}

func TestClientExhaustsRetries(t *testing.T) {
	if testing.Short() {
		t.Skip("退避要等 3.5 秒")
	}
	// Implementation note.
	srv, rec := serveJSON(t, http.StatusServiceUnavailable, `{"error":"down"}`)

	_, err := NewClient(2*time.Second).GetJSON(context.Background(), srv.URL, nil, nil)
	if err == nil || !strings.Contains(err.Error(), "HTTP 503") {
		t.Fatalf("error = %v，expected HTTP 503", err)
	}
	if n := rec.requests(); n != MaxRetries+1 {
		t.Fatalf("请求了 %d 次，expected首次加 %d 次重试", n, MaxRetries)
	}
}

func TestClientTimeoutMessage(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		time.Sleep(300 * time.Millisecond)
		_, _ = io.WriteString(w, `{}`)
	}))
	defer srv.Close()

	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Millisecond)
	defer cancel()

	_, err := NewClient(2*time.Second).GetJSON(ctx, srv.URL, nil, nil)
	if err == nil || err.Error() != "Request timed out" {
		t.Fatalf("error = %v，expected「Request timed out」", err)
	}
}

func TestGetJSONErrors(t *testing.T) {
	t.Run("非 JSON response", func(t *testing.T) {
		srv, _ := serveJSON(t, http.StatusOK, `<html>maintenance</html>`)
		_, err := NewClient(time.Second).GetJSON(context.Background(), srv.URL, nil, nil)
		if err == nil || err.Error() != "Response is not valid JSON" {
			t.Fatalf("error = %v", err)
		}
	})

	t.Run("HTTP 401", func(t *testing.T) {
		srv, _ := serveJSON(t, http.StatusUnauthorized, `{"error":"bad key"}`)
		_, err := NewClient(time.Second).GetJSON(context.Background(), srv.URL, nil, nil)
		if err == nil || !strings.Contains(err.Error(), "HTTP 401: Unauthorized") {
			t.Fatalf("error = %v", err)
		}
	})
}

func TestGetJSONMergesParams(t *testing.T) {
	srv, rec := serveJSON(t, http.StatusOK, `{}`)

	// Implementation note.
	_, err := NewClient(time.Second).GetJSON(context.Background(), srv.URL+"?fixed=1",
		map[string]string{"Accept": "application/json"}, map[string]string{"unit": "usd"})
	if err != nil {
		t.Fatal(err)
	}
	if got := rec.query.Get("fixed"); got != "1" {
		t.Errorf("fixed = %q，原有查询参数被丢了", got)
	}
	if got := rec.query.Get("unit"); got != "usd" {
		t.Errorf("unit = %q", got)
	}
	if got := rec.header.Get("Accept"); got != "application/json" {
		t.Errorf("Accept = %q", got)
	}
}

// Implementation note.

func TestMaskURL(t *testing.T) {
	// Implementation note.
	cases := []struct {
		name string
		in   string
		want string
	}{
		{
			name: "webhook token 留头尾",
			in:   "https://open.feishu.cn/open-apis/bot/v2/hook/abcdef1234567890",
			want: "https://open.feishu.cn/open-apis/bot/v2/hook/abcd***7890",
		},
		{
			name: "短 token 全遮",
			in:   "https://open.feishu.cn/open-apis/bot/v2/hook/abc/send",
			want: "https://open.feishu.cn/open-apis/bot/v2/hook/***/send",
		},
		{
			name: "敏感查询参数",
			in:   "https://oapi.dingtalk.com/robot/send?access_token=1234567890abcdef&sign=x",
			want: "https://oapi.dingtalk.com/robot/send?access_token=1234%2A%2A%2Acdef&sign=x",
		},
		{
			name: "非敏感参数不动",
			in:   "https://data.wxrank.com/weixin/score?key=secretkeyvalue&unit=usd",
			want: "https://data.wxrank.com/weixin/score?key=secr%2A%2A%2Aalue&unit=usd",
		},
		{
			name: "无查询串原样返回",
			in:   "https://api.example.com/v1/x",
			want: "https://api.example.com/v1/x",
		},
		{
			// Implementation note.
			// Implementation note.
			name: "不是 URL 也不能炸",
			in:   "not a url",
			want: "not%20a%20url",
		},
		{
			// Implementation note.
			name: "多个敏感参数",
			in:   "https://api.example.com/x?token=1234567890abcdef&foo=bar",
			want: "https://api.example.com/x?foo=bar&token=1234%2A%2A%2Acdef",
		},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			if got := MaskURL(tc.in); got != tc.want {
				t.Errorf("MaskURL(%q)\n = %q\nexpected %q", tc.in, got, tc.want)
			}
		})
	}
}

func TestSplitKeyPair(t *testing.T) {
	id, secret, err := SplitKeyPair("AKLTxxx:TmpCa01xxx", "Volcengine", "AK:SK")
	if err != nil || id != "AKLTxxx" || secret != "TmpCa01xxx" {
		t.Fatalf("拆出 (%q, %q, %v)", id, secret, err)
	}

	// Implementation note.
	for _, bad := range []string{"AKLTxxx", "", ":SK", "AK:"} {
		if _, _, err := SplitKeyPair(bad, "Volcengine", "AK:SK"); err == nil {
			t.Errorf("%q 应该被判为formaterror", bad)
		} else if !strings.Contains(err.Error(), "Volcengine: invalid API key format; expected 'AK:SK'") {
			t.Errorf("%q 的error message = %q", bad, err.Error())
		}
	}
}
