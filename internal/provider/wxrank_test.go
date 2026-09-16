package provider

import (
	"context"
	"testing"
)

func TestWxRankFetch(t *testing.T) {
	runSpecCases(t, wxrankSpec, []specCase{
		{
			name: "从 msg 文本里抠数字",
			body: `{"code":0,"msg":"剩余263419余额"}`,
			want: 263419,
		},
		{
			name: "msg 里有多段数字取第一段",
			body: `{"code":0,"msg":"剩余100次，共200次"}`,
			want: 100,
		},
		{
			name: "后备：data 直接是数字",
			body: `{"code":0,"msg":"查询成功","data":5000}`,
			want: 5000,
		},
		{
			name: "后备：data.score",
			body: `{"code":0,"msg":"查询成功","data":{"score":1234}}`,
			want: 1234,
		},
		{
			// Python 用的是 `score or credits`，score 是 0 会落到 credits
			name: "后备：score 为 0 时看 credits",
			body: `{"code":0,"msg":"查询成功","data":{"score":0,"credits":66}}`,
			want: 66,
		},
		{
			name: "后备：顶层 score",
			body: `{"code":0,"msg":"查询成功","score":42}`,
			want: 42,
		},
		{
			name:   "业务错误码",
			body:   `{"code":-1,"msg":"密钥无效"}`,
			errMsg: "API 返回错误: 密钥无效",
		},
		{
			name:   "缺少 code 也算失败",
			body:   `{"msg":"缺少 code"}`,
			errMsg: "API 返回错误: 缺少 code",
		},
		{
			name:   "缺少 code 且缺少 msg",
			body:   `{}`,
			errMsg: "API 返回错误: 未知错误",
		},
		{
			// Python 在这里会把 TypeError 的英文原文当错误消息抛给用户，Go 走正常的中文提示
			name:   "msg 不是字符串",
			body:   `{"code":0,"msg":12345}`,
			errMsg: "无法从响应中解析余额",
		},
		{
			name:   "解析不出余额",
			body:   `{"code":0,"msg":"无数据"}`,
			errMsg: "无法从响应中解析余额: 无数据",
		},
	})
}

func TestWxRankPutsKeyInQuery(t *testing.T) {
	// 这家是查询参数鉴权，不是 Bearer
	srv, rec := serveJSON(t, 200, `{"code":0,"msg":"剩余1余额"}`)
	if _, err := specProviderAt(wxrankSpec, srv.URL, "wx-secret").Fetch(context.Background()); err != nil {
		t.Fatal(err)
	}
	if got := rec.query.Get("key"); got != "wx-secret" {
		t.Fatalf("key = %q", got)
	}
	if got := rec.header.Get("Authorization"); got != "" {
		t.Fatalf("不该带 Authorization 头，却带了 %q", got)
	}
}
