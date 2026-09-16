package provider

import (
	"context"
	"testing"
)

func TestUniAPIFetch(t *testing.T) {
	runSpecCases(t, uniapiSpec, []specCase{
		{
			name: "线上真实结构",
			body: `{"success":true,"data":{"balance":10446.05,"used":48280.24,"cache_used":0}}`,
			want: 10446.05,
		},
		{
			name:   "业务失败",
			body:   `{"success":false,"data":{}}`,
			errMsg: "API 返回 success=false",
		},
		{
			name:   "没有 success 字段也算失败",
			body:   `{"data":{"balance":1}}`,
			errMsg: "API 返回 success=false",
		},
		{
			name:   "缺少 balance",
			body:   `{"success":true,"data":{"used":100}}`,
			errMsg: "无法从响应中解析 balance 字段",
		},
		{
			name:   "data 是 null",
			body:   `{"success":true,"data":null}`,
			errMsg: "无法从响应中解析 balance 字段",
		},
	})
}

func TestUniAPISendsUnitParam(t *testing.T) {
	// unit=usd 是接口要求的，漏了会拿到另一种单位的数
	srv, rec := serveJSON(t, 200, `{"success":true,"data":{"balance":1}}`)
	if _, err := specProviderAt(uniapiSpec, srv.URL, "test-key").Fetch(context.Background()); err != nil {
		t.Fatal(err)
	}
	if got := rec.query.Get("unit"); got != "usd" {
		t.Fatalf("unit = %q", got)
	}
	if got := rec.header.Get("Authorization"); got != "Bearer test-key" {
		t.Fatalf("Authorization = %q", got)
	}
}
