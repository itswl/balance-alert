package provider

import (
	"context"
	"testing"
)

func TestGLMFetch(t *testing.T) {
	runSpecCases(t, glmSpec, []specCase{
		{
			// 线上真实结构：TIME_LIMIT 有绝对量，TOKENS_LIMIT 只有百分比，取剩余比例最低者
			name: "多窗口取最紧的那个",
			body: `{"code":200,"msg":"操作成功","success":true,"data":{"level":"pro","limits":[
				{"type":"TIME_LIMIT","unit":5,"number":1,"usage":1000,"currentValue":13,
				 "remaining":987,"percentage":1,"nextResetTime":1790409645998},
				{"type":"TOKENS_LIMIT","unit":3,"number":5,"percentage":0}]}}`,
			want: 98.7,
		},
		{
			name: "新版 CREDIT_LIMIT 结构",
			body: `{"code":200,"msg":"Operation successful","success":true,"data":{"level":"lite","limits":[
				{"type":"CREDIT_LIMIT","unit":3,"number":5,"usage":2000,"currentValue":402,
				 "remaining":1597,"percentage":20},
				{"type":"CREDIT_LIMIT","unit":6,"number":1,"usage":10000,"currentValue":5207,
				 "remaining":4792,"percentage":52}]}}`,
			want: 47.92,
		},
		{
			name: "只有百分比且已用满",
			body: `{"code":200,"success":true,"data":{"limits":[{"type":"TOKENS_LIMIT","percentage":100}]}}`,
			want: 0,
		},
		{
			// usage 为 0 时除不了，退回接口给的已用百分比
			name: "usage 为 0 时用百分比反推",
			body: `{"code":200,"success":true,"data":{"limits":[
				{"type":"CREDIT_LIMIT","usage":0,"remaining":0,"percentage":25}]}}`,
			want: 75,
		},
		{
			name: "异常数据钳制在 0-100",
			body: `{"code":200,"success":true,"data":{"limits":[
				{"type":"CREDIT_LIMIT","usage":100,"remaining":150},
				{"type":"TOKENS_LIMIT","percentage":130}]}}`,
			want: 0,
		},
		{
			name: "没有 code 字段视为成功",
			body: `{"success":true,"data":{"limits":[{"usage":4,"remaining":1}]}}`,
			want: 25,
		},
		{
			name: "算不尽时保留两位小数",
			body: `{"success":true,"data":{"limits":[{"usage":3,"remaining":2}]}}`,
			want: 66.67,
		},
		{
			name:   "业务失败",
			body:   `{"code":401,"msg":"令牌无效","success":false,"data":null}`,
			errMsg: "API 返回错误: 令牌无效",
		},
		{
			name:   "success 为真但 code 不是 200",
			body:   `{"code":500,"msg":"服务异常","success":true}`,
			errMsg: "API 返回错误: 服务异常",
		},
		{
			name:   "缺少 data.limits",
			body:   `{"code":200,"success":true,"data":{"level":"pro"}}`,
			errMsg: "无法从响应中解析 data.limits 字段",
		},
		{
			name:   "limits 里没有能算的窗口",
			body:   `{"code":200,"success":true,"data":{"limits":[{"type":"TOKENS_LIMIT","unit":3,"number":5}]}}`,
			errMsg: "data.limits 里没有可解析的配额窗口",
		},
		{
			name:   "limits 是空列表",
			body:   `{"code":200,"success":true,"data":{"limits":[]}}`,
			errMsg: "data.limits 里没有可解析的配额窗口",
		},
	})
}

func TestGLMSendsBearerToken(t *testing.T) {
	srv, rec := serveJSON(t, 200, `{"success":true,"data":{"limits":[{"percentage":0}]}}`)
	if _, err := specProviderAt(glmSpec, srv.URL, "glm-key").Fetch(context.Background()); err != nil {
		t.Fatal(err)
	}
	if got := rec.header.Get("Authorization"); got != "Bearer glm-key" {
		t.Fatalf("Authorization = %q", got)
	}
}

func TestGLMRemainingPercentIgnoresStringNumbers(t *testing.T) {
	// Python 用 isinstance(x, (int, float)) 判定，字符串 "50" 不算数字；
	// 这里若放宽成 Num 会把字符串也算进去，得出和 Python 不一样的余额
	if _, ok := glmRemainingPercent(map[string]any{"usage": "100", "remaining": "50"}); ok {
		t.Error("字符串的 usage/remaining 不该被当成数字")
	}
	if _, ok := glmRemainingPercent(map[string]any{"percentage": "30"}); ok {
		t.Error("字符串的 percentage 不该被当成数字")
	}
}

func TestRound2MatchesPython(t *testing.T) {
	// 基准取自 Python 的 round(x, 2)：正中间时进偶数，其余按二进制里的真实值定
	cases := []struct{ in, want float64 }{
		{0.125, 0.12}, // 正中间，进偶数
		{0.135, 0.14}, // 二进制里略大于 0.135
		{2.675, 2.67}, // 二进制里略小于 2.675
		{0.005, 0.01}, // 二进制里略大于 0.005
		{98.7, 98.7},  // 本来就够短
		{66.666666, 66.67},
		{33.333333, 33.33},
	}
	for _, tc := range cases {
		if got := round2(tc.in); got != tc.want {
			t.Errorf("round2(%v) = %v，期望 %v", tc.in, got, tc.want)
		}
	}
}
