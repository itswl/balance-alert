package mailscan

import (
	"regexp"
	"strconv"
	"strings"
)

// unknownService 是认不出服务名时的占位。
// 这个字符串会原样出现在告警正文里，改了群里的文案就变了。
const unknownService = "未知服务"

// 服务名一般写在主题的括号里：【阿里云】/ [AWS] / （腾讯云）/ (Azure)。
// 四种括号按这个顺序试，第一种有命中就不再看后面的。
var servicePatterns = []*regexp.Regexp{
	regexp.MustCompile(`【(.+?)】`),
	regexp.MustCompile(`\[(.+?)\]`),
	regexp.MustCompile(`（(.+?)）`),
	regexp.MustCompile(`\((.+?)\)`),
}

// space 是比 \s 更宽的空白类：Go 的 \s 只认 ASCII 空白，而账单邮件从 HTML 转成文本后
// 不换行空格（U+00A0）和全角空格（U+3000）很常见。不把它们算成空白，
// "余额： 12.50 元"这种写法就会整条匹配不上，金额提不出来。
const space = `[\s\p{Z}]`

// 金额提取规则，顺序就是优先级：
// 带"余额/金额"前缀的最可信，最后才退到"裸数字 + 元"这种容易误伤的写法。
var amountPatterns = []*regexp.Regexp{
	regexp.MustCompile(`余额[：:]` + space + `*([0-9,]+\.?[0-9]*)` + space + `*元`),
	regexp.MustCompile(`金额[：:]` + space + `*([0-9,]+\.?[0-9]*)`),
	regexp.MustCompile(`([0-9,]+\.?[0-9]*)` + space + `*元`),
	regexp.MustCompile(`CNY` + space + `*([0-9,]+\.?[0-9]*)`),
}

// extractServiceInfo 从主题的括号里取服务名，从主题加正文里取金额。
// 取不到时分别是 unknownService 与 nil——金额用指针，"没认出来"和"余额为零"不是一回事。
func extractServiceInfo(subject, body string) (string, *float64) {
	service := unknownService
	for _, re := range servicePatterns {
		if m := re.FindStringSubmatch(subject); m != nil {
			service = m[1]
			break
		}
	}

	full := subject + "\n" + body
	for _, re := range amountPatterns {
		m := re.FindStringSubmatch(full)
		if m == nil {
			continue
		}
		amount, err := strconv.ParseFloat(strings.ReplaceAll(m[1], ",", ""), 64)
		if err != nil {
			// 形如 ",,," 的假数字：这条规则不算数，换下一条再试
			continue
		}
		return service, &amount
	}
	return service, nil
}
