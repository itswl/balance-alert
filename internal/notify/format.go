package notify

import (
	"math"
	"strconv"
	"strings"
	"time"
)

// 数字写法是对外契约的一部分：群里的人是按位数扫一眼就判断"这个数对不对"的，
// 千位分隔没了、或者 20.0 被写成了 20，都会让人以为数值变了。

// formatAmount 千位分隔 + 固定两位小数，形如 "1,234.50"。告警里的余额和阈值都走它。
func formatAmount(v float64) string {
	if s, ok := nonFinite(v); ok {
		return s
	}

	s := strconv.FormatFloat(v, 'f', 2, 64)
	sign := ""
	if strings.HasPrefix(s, "-") {
		sign, s = "-", s[1:]
	}
	whole, frac, _ := strings.Cut(s, ".")
	return sign + group(whole) + "." + frac
}

// group 每三位插一个逗号。
func group(digits string) string {
	if len(digits) <= 3 {
		return digits
	}
	var b strings.Builder
	head := len(digits) % 3
	if head > 0 {
		b.WriteString(digits[:head])
	}
	for i := head; i < len(digits); i += 3 {
		if b.Len() > 0 {
			b.WriteByte(',')
		}
		b.WriteString(digits[i : i+3])
	}
	return b.String()
}

// formatFloat 用最短可往返的写法，整数值补 ".0"：订阅金额 20 拼进文本就是 "20.0"。
//
// 不能图省事用 %g：它在 100 万以上就换成科学计数法，群里会看到 "1.234567e+06"
// 这种没人愿意读的金额。这里要到 1e16 才换成科学计数法。
func formatFloat(v float64) string {
	if s, ok := nonFinite(v); ok {
		return s
	}

	sci := strconv.FormatFloat(v, 'e', -1, 64) // 形如 "1.599e+01"
	_, expText, _ := strings.Cut(sci, "e")
	exp, err := strconv.Atoi(expText)
	if err == nil && (exp < -4 || exp >= 16) {
		return sci // 这个区间外的数值写成十进制也没人读得动，直接给科学计数法
	}

	s := strconv.FormatFloat(v, 'f', -1, 64)
	if !strings.Contains(s, ".") {
		s += ".0"
	}
	return s
}

// nonFinite 把 NaN / Inf 单独挑出来，写成 "nan" / "inf" / "-inf"。
// 不挡在前面的话，上面按小数点切分的逻辑会输出 "NaN." 这种半截结果。
func nonFinite(v float64) (string, bool) {
	switch {
	case math.IsNaN(v):
		return "nan", true
	case math.IsInf(v, 1):
		return "inf", true
	case math.IsInf(v, -1):
		return "-inf", true
	}
	return "", false
}

// isoLocal 按 ISO 8601 写本地时间：不带时区，微秒为 0 时连小数部分一起省掉。
// 自定义 webhook 报文里的 timestamp 就是这个格式，接收端按它解析。
func isoLocal(t time.Time) string {
	if t.Nanosecond()/1000 == 0 {
		return t.Format("2006-01-02T15:04:05")
	}
	return t.Format("2006-01-02T15:04:05.000000")
}
