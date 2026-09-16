package subscription

import (
	"encoding/json"
	"os"
	"testing"
	"time"
)

// pythonCase 是从 Python 版跑出来的对照数据，用来证明两边的日期推算完全一致。
// 生成方式见 testdata/python_cases.json 的来源：调用 SubscriptionChecker 的内部方法穷举组合。
type pythonCase struct {
	Cycle          string  `json:"cycle"`
	RenewalDay     int     `json:"renewal_day"`
	Today          string  `json:"today"`
	LastRenewed    *string `json:"last_renewed"`
	Days           int     `json:"days"`
	Next           string  `json:"next"`
	AlreadyRenewed bool    `json:"already_renewed"`
}

// TestMatchesPythonBaseline 是这个包最重要的测试：385 组日期边界逐一对齐旧实现。
// 闰年、月末、跨年、已续费判断都在里面，改坏任何一处都会在这里炸出来。
func TestMatchesPythonBaseline(t *testing.T) {
	raw, err := os.ReadFile("testdata/python_cases.json")
	if err != nil {
		t.Fatalf("读取对照数据失败: %v", err)
	}
	var cases []pythonCase
	if err := json.Unmarshal(raw, &cases); err != nil {
		t.Fatalf("解析对照数据失败: %v", err)
	}
	if len(cases) < 300 {
		t.Fatalf("对照数据只有 %d 条，太少，怀疑生成有问题", len(cases))
	}

	for _, c := range cases {
		today := mustDate(t, c.Today)
		var lastRenewed *time.Time
		if c.LastRenewed != nil {
			parsed := mustDate(t, *c.LastRenewed)
			lastRenewed = &parsed
		}

		days, next := NextRenewal(c.Cycle, c.RenewalDay, today, lastRenewed)
		if days != c.Days || next.Format("2006-01-02") != c.Next {
			t.Errorf("%s/%d 在 %s（上次续费 %v）: 期望 %d 天后的 %s，实际 %d 天后的 %s",
				c.Cycle, c.RenewalDay, c.Today, derefString(c.LastRenewed),
				c.Days, c.Next, days, next.Format("2006-01-02"))
			continue
		}

		already := false
		if lastRenewed != nil {
			start := cycleStart(c.Cycle, c.RenewalDay, startOfDay(today), next)
			already = !lastRenewed.Before(start)
		}
		if already != c.AlreadyRenewed {
			t.Errorf("%s/%d 在 %s（上次续费 %v）: 已续费判断期望 %v，实际 %v",
				c.Cycle, c.RenewalDay, c.Today, derefString(c.LastRenewed), c.AlreadyRenewed, already)
		}
	}
}

func TestSplitMMDD(t *testing.T) {
	tests := []struct {
		input       int
		month, day  int
		ok          bool
		explanation string
	}{
		{315, 3, 15, true, "3 月 15 日"},
		{1231, 12, 31, true, "12 月 31 日"},
		{229, 2, 29, true, "2 月 29 日"},
		{15, 0, 0, false, "小于 31 属于旧配置的只写了日"},
		{31, 0, 0, false, "边界：31 仍算旧配置"},
		{1350, 0, 0, false, "13 月不存在"},
		{300, 0, 0, false, "0 日不存在"},
	}
	for _, tt := range tests {
		month, day, ok := SplitMMDD(tt.input)
		if ok != tt.ok || (ok && (month != tt.month || day != tt.day)) {
			t.Errorf("SplitMMDD(%d) = %d,%d,%v；期望 %d,%d,%v（%s）",
				tt.input, month, day, ok, tt.month, tt.day, tt.ok, tt.explanation)
		}
	}
}

func TestCoerceRenewalDay(t *testing.T) {
	tests := []struct {
		input, cycle string
		want         int
		ok           bool
	}{
		{"03-15", "yearly", 315, true},
		{"3-15", "yearly", 315, true},
		{"3月15日", "yearly", 315, true},
		{"03/15", "yearly", 315, true},
		{"03-15", "monthly", 15, true},
		{"15", "monthly", 15, true},
		{" 7 ", "weekly", 7, true},
		{"每月十五", "monthly", 0, false},
		{"", "monthly", 0, false},
	}
	for _, tt := range tests {
		got, ok := CoerceRenewalDay(tt.input, tt.cycle)
		if got != tt.want || ok != tt.ok {
			t.Errorf("CoerceRenewalDay(%q, %q) = %d,%v；期望 %d,%v", tt.input, tt.cycle, got, ok, tt.want, tt.ok)
		}
	}
}

// TestMonthEndClamping 单独盯住月末回退，这是最容易改坏的一处。
func TestMonthEndClamping(t *testing.T) {
	// 1 月 31 日订阅，站在 2 月 1 日看，下次应该落在 2 月末而不是 3 月 3 日
	_, next := NextRenewal("monthly", 31, mustDate(t, "2026-02-01"), nil)
	if got := next.Format("2006-01-02"); got != "2026-02-28" {
		t.Errorf("31 号的月付在 2 月应回退到 2026-02-28，实际 %s", got)
	}
	// 闰年 2 月 29 日的年付，在平年应落到 2 月 28 日
	last := mustDate(t, "2024-02-29")
	_, next = NextRenewal("yearly", 229, mustDate(t, "2026-01-01"), &last)
	if got := next.Format("2006-01-02"); got != "2026-02-28" {
		t.Errorf("2 月 29 日的年付在平年应回退到 2026-02-28，实际 %s", got)
	}
}

// TestRenewalDayIsNotOffByOne 续费当天必须算 0 天而不是 -1 天，否则当天收不到提醒。
func TestRenewalDayIsNotOffByOne(t *testing.T) {
	today := time.Date(2026, 3, 15, 14, 30, 0, 0, time.Local) // 故意带上时分秒
	days, next := NextRenewal("monthly", 15, today, nil)
	if days != 0 || next.Format("2006-01-02") != "2026-03-15" {
		t.Errorf("续费当天应为 0 天（2026-03-15），实际 %d 天（%s）", days, next.Format("2006-01-02"))
	}
}

func mustDate(t *testing.T, value string) time.Time {
	t.Helper()
	parsed, err := time.ParseInLocation("2006-01-02", value, time.Local)
	if err != nil {
		t.Fatalf("测试数据里的日期解析失败 %q: %v", value, err)
	}
	return parsed
}

func derefString(p *string) string {
	if p == nil {
		return "无"
	}
	return *p
}
