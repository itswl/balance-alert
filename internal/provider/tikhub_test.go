package provider

import (
	"context"
	"testing"
)

func TestTikHubFetch(t *testing.T) {
	runSpecCases(t, tikhubSpec, []specCase{
		{
			name: "user_data 结构",
			body: `{"code":200,"user_data":{"balance":99.5}}`,
			want: 99.5,
		},
		{
			name: "data 结构回退",
			body: `{"data":{"balance":50.0}}`,
			want: 50.0,
		},
		{
			name: "平铺结构回退",
			body: `{"balance":20.0}`,
			want: 20.0,
		},
		{
			name: "user_data 优先于 data",
			body: `{"user_data":{"balance":1},"data":{"balance":2}}`,
			want: 1,
		},
		{
			name:   "Missing balance",
			body:   `{"user_data":{"name":"test"}}`,
			errMsg: "Could not parse balance field",
		},
		{
			name:   "user_data 是 null 就不再往下找",
			body:   `{"user_data":null,"balance":20.0}`,
			errMsg: "Could not parse balance field",
		},
		{
			name:   "禁止访问",
			status: 403,
			body:   `{"detail":"forbidden"}`,
			errMsg: "HTTP 403",
		},
	})
}

func TestTikHubSendsAcceptHeader(t *testing.T) {
	srv, rec := serveJSON(t, 200, `{"user_data":{"balance":1}}`)
	if _, err := specProviderAt(tikhubSpec, srv.URL, "test-key").Fetch(context.Background()); err != nil {
		t.Fatal(err)
	}
	if got := rec.header.Get("Accept"); got != "application/json" {
		t.Fatalf("Accept = %q", got)
	}
}
