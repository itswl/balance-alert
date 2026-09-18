package provider

import (
	"context"
	"testing"
)

func TestOpenRouterFetch(t *testing.T) {
	runSpecCases(t, openRouterSpec, []specCase{
		{
			name: "嵌套 data 结构",
			body: `{"data":{"total_credits":100.0,"total_usage":25.5}}`,
			want: 74.5,
		},
		{
			name: "平铺结构",
			body: `{"total_credits":50.0,"total_usage":10.0}`,
			want: 40.0,
		},
		{
			name: "用满了是 0 不是负数以外的怪值",
			body: `{"data":{"total_credits":10,"total_usage":10}}`,
			want: 0,
		},
		{
			name:   "Missing total_credits",
			body:   `{"data":{"total_usage":25.5}}`,
			errMsg: "Could not parse total_credits field",
		},
		{
			name:   "Missing total_usage",
			body:   `{"data":{"total_credits":100.0}}`,
			errMsg: "Could not parse total_usage field",
		},
		{
			name:   "data 是 null",
			body:   `{"data":null}`,
			errMsg: "Could not parse total_credits field",
		},
		{
			name:   "密钥无效",
			status: 401,
			body:   `{"error":"unauthorized"}`,
			errMsg: "HTTP 401",
		},
	})
}

func TestOpenRouterSendsBearerToken(t *testing.T) {
	srv, rec := serveJSON(t, 200, `{"data":{"total_credits":1,"total_usage":0}}`)
	if _, err := specProviderAt(openRouterSpec, srv.URL, "sk-or-test").Fetch(context.Background()); err != nil {
		t.Fatal(err)
	}
	if got := rec.header.Get("Authorization"); got != "Bearer sk-or-test" {
		t.Fatalf("Authorization = %q", got)
	}
}
