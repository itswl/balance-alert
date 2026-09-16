package report

import (
	"encoding/json"
	"os"
	"testing"
	"time"

	"github.com/itswl/balance-alert/internal/model"
)

func ptr[T any](v T) *T { return &v }

// buildFixture 与 testdata/python_case.json 用的是同一份输入，两边渲染结果必须一致。
func buildFixture() Summary {
	results := []model.CheckResult{
		{Project: "deepseek", Provider: "deepseek", Success: true, Credits: ptr(100.0), Threshold: ptr(50.0)},
		{Project: "glm", Provider: "glm", Success: true, Credits: ptr(8.0), Threshold: ptr(10.0), NeedAlarm: true},
		{Project: "volc", Provider: "volc", Success: true, Credits: ptr(3000.0), Threshold: ptr(1000.0)},
		{Project: "aliyun", Provider: "aliyun", Success: true, Credits: ptr(500.0), Threshold: ptr(100.0)},
		{Project: "tikhub", Provider: "tikhub", Success: false, Error: ptr("HTTP 401: Unauthorized")},
	}
	subs := []model.SubscriptionResult{
		{Name: "域名续费", DaysUntilRenewal: 5, Amount: 88},
		{Name: "Netflix", DaysUntilRenewal: 20, Amount: 99},
		{Name: "已续过的", DaysUntilRenewal: 3, Amount: 50, AlreadyRenewed: true},
		{Name: "太远的", DaysUntilRenewal: 60, Amount: 200},
	}
	mailboxes := []model.MailboxResult{{Name: "a"}, {Name: "b", Error: ptr("连不上")}}

	runways := map[string]model.Runway{
		model.ProjectID("deepseek", "deepseek"): {Consumed: 437.5, BurnPerDay: ptr(62.5), RunwayDays: ptr(1.6), DepletionDate: ptr("2026-09-18"), CurrentBalance: ptr(100.0)},
		model.ProjectID("glm", "glm"):           {Consumed: 12, BurnPerDay: ptr(1.7), RunwayDays: ptr(4.7), DepletionDate: ptr("2026-09-21"), CurrentBalance: ptr(8.0)},
		model.ProjectID("volc", "volc"):         {Consumed: 1200, BurnPerDay: ptr(171.4), RunwayDays: ptr(17.5), DepletionDate: ptr("2026-10-04"), CurrentBalance: ptr(3000.0)},
		model.ProjectID("aliyun", "aliyun"):     {Consumed: 50, BurnPerDay: ptr(7.1), CurrentBalance: ptr(500.0)},
	}

	now := time.Date(2026, 9, 16, 12, 0, 0, 0, time.Local)
	return Build(results, subs, mailboxes, 3, runways, now)
}

// TestRenderMatchesPython 整张卡片逐字对齐旧实现。用户的飞书群里看惯了这个格式。
func TestRenderMatchesPython(t *testing.T) {
	raw, err := os.ReadFile("testdata/python_case.json")
	if err != nil {
		t.Fatalf("读取对照数据失败: %v", err)
	}
	var baseline struct {
		Rendered string `json:"rendered"`
		Summary  struct {
			TotalConsumed  float64 `json:"total_consumed"`
			UpcomingAmount float64 `json:"upcoming_amount"`
		} `json:"summary"`
	}
	if err := json.Unmarshal(raw, &baseline); err != nil {
		t.Fatalf("解析对照数据失败: %v", err)
	}

	summary := buildFixture()
	if got := Render(summary); got != baseline.Rendered {
		t.Errorf("渲染结果与旧实现不一致。\n期望:\n%s\n\n实际:\n%s", baseline.Rendered, got)
	}
	if summary.TotalConsumed == nil || *summary.TotalConsumed != baseline.Summary.TotalConsumed {
		t.Errorf("本周消耗: 期望 %v，实际 %v", baseline.Summary.TotalConsumed, summary.TotalConsumed)
	}
	if summary.UpcomingAmount != baseline.Summary.UpcomingAmount {
		t.Errorf("待续费金额: 期望 %v，实际 %v", baseline.Summary.UpcomingAmount, summary.UpcomingAmount)
	}
}

// TestUpcomingExcludesRenewedAndDistant 已续过的和一个月以外的不该算进待续费。
func TestUpcomingExcludesRenewedAndDistant(t *testing.T) {
	summary := buildFixture()
	if len(summary.UpcomingSubscriptions) != 2 {
		t.Fatalf("待续费应只有 2 条，实际 %d 条", len(summary.UpcomingSubscriptions))
	}
	if summary.UpcomingSubscriptions[0].Name != "域名续费" {
		t.Error("待续费应按紧迫程度排序，最急的在前")
	}
}

// TestTopNIsCapped 排行榜各取前三，账户再多也不会刷屏。
func TestTopNIsCapped(t *testing.T) {
	summary := buildFixture()
	if len(summary.TopSpend) != TopN {
		t.Errorf("消耗榜应有 %d 条，实际 %d", TopN, len(summary.TopSpend))
	}
	if summary.TopSpend[0].Project != "volc" {
		t.Errorf("消耗最多的应是 volc，实际 %s", summary.TopSpend[0].Project)
	}
	// aliyun 没有跑道天数，不该出现在"最先见底"里
	for _, row := range summary.ShortestRunway {
		if row.Project == "aliyun" {
			t.Error("没有跑道估算的账户不该上见底榜")
		}
	}
}

// TestEmptySectionsAreOmitted 没内容的小节整段不出现，卡片不能一堆空标题。
func TestEmptySectionsAreOmitted(t *testing.T) {
	now := time.Date(2026, 9, 16, 12, 0, 0, 0, time.Local)
	summary := Build(
		[]model.CheckResult{{Project: "a", Provider: "p", Success: true, Credits: ptr(10.0), Threshold: ptr(1.0)}},
		nil, nil, 0, nil, now)

	rendered := Render(summary)
	for _, unwanted := range []string{"最先见底", "消耗最多", "需要处理"} {
		if contains(rendered, unwanted) {
			t.Errorf("没有内容时不该出现「%s」小节：\n%s", unwanted, rendered)
		}
	}
	if !contains(rendered, "全部正常") {
		t.Errorf("没有告警时应说全部正常：\n%s", rendered)
	}
	if summary.TotalConsumed != nil {
		t.Error("没有历史时不该给出本周消耗")
	}
}

func TestThousandsSeparator(t *testing.T) {
	tests := []struct {
		value float64
		want  string
	}{
		{0, "0.00"},
		{8, "8.00"},
		{1234.5, "1,234.50"},
		{1234567.89, "1,234,567.89"},
		{-1234.5, "-1,234.50"},
		{999, "999.00"},
		{1000, "1,000.00"},
	}
	for _, tt := range tests {
		if got := thousands(tt.value, 2); got != tt.want {
			t.Errorf("thousands(%v) = %q，期望 %q", tt.value, got, tt.want)
		}
	}
	if got := fmtNum(nil); got != "-" {
		t.Errorf("空值应显示成横杠，实际 %q", got)
	}
}

func contains(haystack, needle string) bool {
	return len(haystack) >= len(needle) && indexOf(haystack, needle) >= 0
}

func indexOf(haystack, needle string) int {
	for i := 0; i+len(needle) <= len(haystack); i++ {
		if haystack[i:i+len(needle)] == needle {
			return i
		}
	}
	return -1
}
