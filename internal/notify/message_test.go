package notify

import (
	"reflect"
	"strings"
	"testing"
	"time"
)

// 消息模板的快照。正文里每一行的字段、顺序和数字写法都是值班群认的样子，
// 这里逐字钉死——改模板必须是有意的，不能是顺手改出来的。

func TestMessageTemplates(t *testing.T) {
	owner := "核心业务"
	service := "OpenAI"
	amount := 20.0

	tests := []struct {
		name      string
		msg       Message
		wantTitle string
		wantKind  string
		wantLines []string
	}{
		{
			name:      "余额告警",
			msg:       BalanceAlert("TestProject", &owner, "OpenRouter", 1234.5, 10000.0),
			wantTitle: "余额告警",
			wantKind:  KindBalance,
			wantLines: []string{
				"API 调用: TestProject",
				"所属项目: 核心业务",
				"服务商: OpenRouter",
				"当前余额: 1,234.50",
				"告警阈值: 10,000.00",
				"状态: ⚠️ 余额不足",
			},
		},
		{
			name:      "余额告警_没有所属项目就不出这一行",
			msg:       BalanceAlert("TestProject", nil, "OpenRouter", 5.0, 10.0),
			wantTitle: "余额告警",
			wantKind:  KindBalance,
			wantLines: []string{
				"API 调用: TestProject",
				"服务商: OpenRouter",
				"当前余额: 5.00",
				"告警阈值: 10.00",
				"状态: ⚠️ 余额不足",
			},
		},
		{
			name:      "订阅提醒_月付",
			msg:       SubscriptionAlert("Netflix", &owner, "monthly", 15, 3, 15.99),
			wantTitle: "订阅续费提醒",
			wantKind:  KindSubscription,
			wantLines: []string{
				"订阅: Netflix",
				"所属项目: 核心业务",
				"续费周期: 每月 15 号",
				"距离续费: 3 天后",
				"续费金额: 15.99",
			},
		},
		{
			name:      "订阅提醒_年付今天到期",
			msg:       SubscriptionAlert("ChatGPT", nil, "yearly", 315, 0, 20.0),
			wantTitle: "订阅续费提醒",
			wantKind:  KindSubscription,
			wantLines: []string{
				"订阅: ChatGPT",
				"续费周期: 每年 3月15日",
				"距离续费: 今天",
				"续费金额: 20.0",
			},
		},
		{
			name: "邮件命中",
			msg: EmailAlert("财务邮箱", "Your receipt from OpenAI", "billing@openai.com",
				"2026-09-16 10:00:00", []string{"invoice", "续费"}, &service, &amount),
			wantTitle: "📧 邮件告警: Your receipt from OpenAI",
			wantKind:  KindEmail,
			wantLines: []string{
				"**邮箱**: 财务邮箱",
				"**发件人**: billing@openai.com",
				"**日期**: 2026-09-16 10:00:00",
				"**服务**: OpenAI",
				"**金额**: 20.0",
				"**关键词**: invoice, 续费",
			},
		},
		{
			// 认不出服务名时正文里写字面量 None，金额缺失则整行不出现
			name: "邮件命中_服务未识别且无金额",
			msg: EmailAlert("", "账单", "noreply@x.com", "2026-09-16",
				[]string{"账单"}, nil, nil),
			wantTitle: "📧 邮件告警: 账单",
			wantKind:  KindEmail,
			wantLines: []string{
				"**邮箱**: 未知",
				"**发件人**: noreply@x.com",
				"**日期**: 2026-09-16",
				"**服务**: None",
				"**关键词**: 账单",
			},
		},
		{
			name: "邮箱连接失败",
			msg: mailboxError("财务邮箱", "[Errno 61] Connection refused",
				time.Date(2026, 9, 16, 23, 45, 1, 0, time.Local)),
			wantTitle: "❌ 邮箱连接失败告警",
			wantKind:  KindMailboxError,
			wantLines: []string{
				"**邮箱**: 财务邮箱",
				"**错误信息**: [Errno 61] Connection refused",
				"**时间**: 2026-09-16 23:45:01",
			},
		},
		{
			name:      "富文本告警原样透传",
			msg:       Custom("余额周报", []string{"**统计区间**: 09-09 ~ 09-16"}, KindWeeklyReport),
			wantTitle: "余额周报",
			wantKind:  KindWeeklyReport,
			wantLines: []string{"**统计区间**: 09-09 ~ 09-16"},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if tt.msg.Title != tt.wantTitle {
				t.Errorf("Title = %q，期望 %q", tt.msg.Title, tt.wantTitle)
			}
			if tt.msg.Kind != tt.wantKind {
				t.Errorf("Kind = %q，期望 %q", tt.msg.Kind, tt.wantKind)
			}
			if !reflect.DeepEqual(tt.msg.Lines, tt.wantLines) {
				t.Errorf("正文不一致\n期望: %q\n实际: %q", tt.wantLines, tt.msg.Lines)
			}
		})
	}
}

// 金额为 0 等同于"没认出金额"，整行不出现——群里看到 "**金额**: 0.0" 只会让人多查一遍。
func TestEmailAlertSkipsZeroAmount(t *testing.T) {
	zero := 0.0
	msg := EmailAlert("m", "s", "from", "date", []string{"k"}, nil, &zero)
	for _, line := range msg.Lines {
		if line == "**金额**: 0.0" {
			t.Fatalf("金额为 0 不该出现在正文里: %q", msg.Lines)
		}
	}
}

// MailboxError 的时间取当前时刻；host 只是调用方的上下文，不进正文。
func TestMailboxErrorUsesNowAndDropsHost(t *testing.T) {
	before := time.Now().Truncate(time.Second)
	msg := MailboxError("财务邮箱", "imap.exmail.qq.com", "[Errno 61] Connection refused")
	after := time.Now()

	if len(msg.Lines) != 3 {
		t.Fatalf("正文应当是三行，实际 %q", msg.Lines)
	}
	for _, line := range msg.Lines {
		if strings.Contains(line, "imap.exmail.qq.com") {
			t.Errorf("host 不该出现在正文里: %q", line)
		}
	}

	at, err := time.ParseInLocation("2006-01-02 15:04:05",
		strings.TrimPrefix(msg.Lines[2], "**时间**: "), time.Local)
	if err != nil {
		t.Fatalf("时间行格式不对: %q", msg.Lines[2])
	}
	if at.Before(before) || at.After(after) {
		t.Errorf("时间 %v 不在 [%v, %v] 之间", at, before, after)
	}
}

func TestFormatSubscriptionCycle(t *testing.T) {
	tests := []struct {
		cycleType  string
		renewalDay int
		want       string
	}{
		{"weekly", 1, "每周 周一"},
		{"weekly", 7, "每周 周日"},
		{"weekly", 9, "每周第 9 天"}, // 越界不猜，原样说出来
		{"monthly", 15, "每月 15 号"},
		{"monthly", 31, "每月 31 号"},
		{"yearly", 315, "每年 3月15日"},
		{"yearly", 1231, "每年 12月31日"},
		{"yearly", 1, "每年固定日期"},    // 旧配置只写了日
		{"yearly", 1350, "每年固定日期"}, // 13 月不是合法 MMDD
		{"bogus", 15, "未知周期"},      // 调用方靠这个值把配置问题报出来
		{"", 15, "未知周期"},
	}

	for _, tt := range tests {
		if got := FormatSubscriptionCycle(tt.cycleType, tt.renewalDay); got != tt.want {
			t.Errorf("FormatSubscriptionCycle(%q, %d) = %q，期望 %q",
				tt.cycleType, tt.renewalDay, got, tt.want)
		}
	}
}

func TestFormatDays(t *testing.T) {
	tests := []struct {
		days int
		want string
	}{
		{0, "今天"},
		{1, "明天"},
		{2, "2 天后"},
		{30, "30 天后"},
		{-1, "-1 天后"}, // 已经过期的订阅就这么写，不做特殊措辞
	}

	for _, tt := range tests {
		if got := formatDays(tt.days); got != tt.want {
			t.Errorf("formatDays(%d) = %q，期望 %q", tt.days, got, tt.want)
		}
	}
}

// 千位分隔 + 固定两位小数，下面每条都是一个边界。
func TestFormatAmount(t *testing.T) {
	tests := []struct {
		value float64
		want  string
	}{
		{0, "0.00"},
		{5, "5.00"},
		{999.994, "999.99"},
		{1234.5, "1,234.50"},
		{10000, "10,000.00"},
		{1000000, "1,000,000.00"},
		{1234567.891, "1,234,567.89"},
		{2.675, "2.67"}, // 二进制里存的比 2.675 略小，进不上去
		{-1234.5, "-1,234.50"},
		{1e-5, "0.00"},
	}

	for _, tt := range tests {
		if got := formatAmount(tt.value); got != tt.want {
			t.Errorf("formatAmount(%v) = %q，期望 %q", tt.value, got, tt.want)
		}
	}
}

// 最短可往返的写法，整数补 ".0"。订阅金额就是这么拼进文本的。
func TestFormatFloat(t *testing.T) {
	tests := []struct {
		value float64
		want  string
	}{
		{0, "0.0"},
		{20, "20.0"},
		{15.99, "15.99"},
		{1234.5, "1234.5"},
		{1234567, "1234567.0"}, // 换成 %g 这里就成了 1.234567e+06
		{0.30000000000000004, "0.30000000000000004"}, // 精度尾巴要原样留着，别被四舍五入抹平
		{1e16, "1e+16"},
		{1e-5, "1e-05"},
		{-1234.5, "-1234.5"},
	}

	for _, tt := range tests {
		if got := formatFloat(tt.value); got != tt.want {
			t.Errorf("formatFloat(%v) = %q，期望 %q", tt.value, got, tt.want)
		}
	}
}

func TestISOLocal(t *testing.T) {
	withMicros := time.Date(2026, 9, 16, 23, 50, 26, 26504000, time.Local)
	if got, want := isoLocal(withMicros), "2026-09-16T23:50:26.026504"; got != want {
		t.Errorf("isoLocal = %q，期望 %q", got, want)
	}
	// 微秒为 0 时不写小数部分
	whole := time.Date(2026, 9, 16, 23, 50, 26, 0, time.Local)
	if got, want := isoLocal(whole), "2026-09-16T23:50:26"; got != want {
		t.Errorf("isoLocal = %q，期望 %q", got, want)
	}
}
