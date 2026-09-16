package mailscan

import (
	"regexp"
	"strings"
)

// DefaultAlertKeywords 是默认的告警关键词表，与 Python 版 DEFAULT_ALERT_KEYWORDS 逐字一致。
//
// 上层用 EMAIL_ALERT_KEYWORDS 整体替换它、EMAIL_EXTRA_ALERT_KEYWORDS 在其上追加。
// 表的顺序有意义：命中结果按这张表的顺序输出，同一处文本上排在前面的词先命中。
var DefaultAlertKeywords = []string{
	// 中文关键词
	"欠费", "余额不足", "余额预警", "余额告警",
	"即将到期", "已到期", "续费提醒", "续费通知",
	"账单逾期", "缴费通知", "请及时续费", "停机",
	"暂停服务", "服务即将暂停", "充值提醒",
	// 英文关键词
	"overdue", "past due", "payment due", "payment overdue",
	"low balance", "insufficient balance", "balance alert",
	"expiring soon", "expired", "expiration notice",
	"renewal reminder", "renewal notice", "renew now",
	"payment reminder", "payment required", "bill overdue",
	"service suspension", "service suspended", "suspended",
	"recharge reminder", "top up", "account suspended",
	"unpaid invoice", "outstanding balance", "payment failed",
}

// matcher 判断一封邮件是不是告警邮件。
//
// 和 Python 版一样把整张词表拼成一条"或"正则，扫一遍主题加正文：
// 交替分支从左到右取第一个命中的，"payment overdue" 因此会整体命中，
// 而不会先被 "overdue" 切掉半截。逐个词 strings.Contains 得不到这个效果。
type matcher struct {
	keywords []string
	re       *regexp.Regexp
}

func newMatcher(keywords []string) *matcher {
	parts := make([]string, 0, len(keywords))
	for _, kw := range keywords {
		if kw == "" {
			// 空词会让正则在任何位置都命中空串，等于整张表作废
			continue
		}
		parts = append(parts, regexp.QuoteMeta(strings.ToLower(kw)))
	}
	if len(parts) == 0 {
		return &matcher{keywords: keywords}
	}
	return &matcher{
		keywords: keywords,
		re:       regexp.MustCompile("(?i)" + strings.Join(parts, "|")),
	}
}

// match 返回命中的关键词，保持词表里的原始大小写与顺序。
func (m *matcher) match(subject, body string) []string {
	if m.re == nil {
		return nil
	}
	found := m.re.FindAllString(subject+"\n"+body, -1)
	if len(found) == 0 {
		return nil
	}

	hit := make(map[string]bool, len(found))
	for _, f := range found {
		hit[strings.ToLower(f)] = true
	}
	matched := make([]string, 0, len(hit))
	for _, kw := range m.keywords {
		if hit[strings.ToLower(kw)] {
			matched = append(matched, kw)
		}
	}
	return matched
}
