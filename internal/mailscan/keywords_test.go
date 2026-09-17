package mailscan

import (
	"slices"
	"testing"
)

// 默认词表是产品行为的一部分：漏一个词就少一类告警，多一个词就多一批误报。
// 数量对不上说明有人顺手改了表，改之前先想清楚会多出还是少掉哪一类告警。
func TestDefaultAlertKeywordsIsUnchanged(t *testing.T) {
	if got, want := len(DefaultAlertKeywords), 40; got != want {
		t.Fatalf("默认关键词数量 = %d, 期望 %d", got, want)
	}
	for _, kw := range []string{"欠费", "余额不足", "停机", "overdue", "payment failed"} {
		if !slices.Contains(DefaultAlertKeywords, kw) {
			t.Errorf("默认关键词表里少了 %q", kw)
		}
	}
}

func TestMatchKeywords(t *testing.T) {
	m := newMatcher(DefaultAlertKeywords)

	tests := []struct {
		name    string
		subject string
		body    string
		want    []string
	}{
		{"中文关键词在主题里", "您的账户余额不足", "", []string{"余额不足"}},
		{"中文关键词在正文里", "通知", "您的服务已欠费，请及时充值", []string{"欠费"}},
		{"英文关键词", "Payment Overdue Notice", "", []string{"payment overdue"}},
		{"英文关键词在正文里", "", "Your account has a low balance", []string{"low balance"}},
		{"expired", "Your subscription has expired", "", []string{"expired"}},
		{"大小写不敏感", "PAYMENT DUE", "", []string{"payment due"}},
		{"多个关键词按词表顺序返回", "余额不足告警", "您的账户已欠费，请及时续费",
			[]string{"欠费", "余额不足", "请及时续费"}},
		{"续费提醒", "续费提醒", "", []string{"续费提醒"}},
		{"suspended", "", "Your account has been suspended", []string{"suspended"}},
		{"跨主题和正文查找", "服务通知", "余额预警：当前余额低于阈值", []string{"余额预警"}},
		{"没有关键词", "周报通知", "本周工作总结", nil},
		{"空邮件", "", "", nil},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := m.match(tt.subject, tt.body)
			if !slices.Equal(got, tt.want) {
				t.Errorf("match(%q, %q) = %v, 期望 %v", tt.subject, tt.body, got, tt.want)
			}
		})
	}
}

// 一条"或"正则从左到右取第一个命中的分支，长词整体命中，不会再被它的子串重复统计一次。
func TestMatchKeywordsTakesLongestPhrase(t *testing.T) {
	m := newMatcher(DefaultAlertKeywords)

	got := m.match("Payment Overdue Notice", "")
	if slices.Contains(got, "overdue") {
		t.Errorf("match = %v, 不该把 %q 再单独算一次", got, "overdue")
	}

	got = m.match("", "Your account suspended yesterday")
	if !slices.Equal(got, []string{"account suspended"}) {
		t.Errorf("match = %v, 期望只命中 %q", got, "account suspended")
	}
}

func TestMatchKeywordsCustomList(t *testing.T) {
	m := newMatcher([]string{"Renew", "配额不足"})
	if got, want := m.match("请尽快 renew", "配额不足"), []string{"Renew", "配额不足"}; !slices.Equal(got, want) {
		t.Errorf("match = %v, 期望 %v（保持词表里的原始大小写与顺序）", got, want)
	}
	if got := m.match("余额不足", "欠费"); got != nil {
		t.Errorf("match = %v, 自定义词表应当整体替换默认词表", got)
	}
}

// 空词会让正则在任何位置命中空串，等于整张表作废——必须在编译词表时就丢掉。
func TestMatchKeywordsIgnoresEmptyWords(t *testing.T) {
	m := newMatcher([]string{"", "欠费"})
	if got, want := m.match("已欠费", ""), []string{"欠费"}; !slices.Equal(got, want) {
		t.Errorf("match = %v, 期望 %v", got, want)
	}
	if got := newMatcher([]string{"", ""}).match("欠费", "任何内容"); got != nil {
		t.Errorf("match = %v, 词表全空时不该有命中", got)
	}
}
