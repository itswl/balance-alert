package notify

import (
	"math"
	"strconv"
	"strings"
	"time"
)

// 数字写法要和 Python 版一模一样：群里的人是按位数扫一眼就判断"这个数对不对"的，
// 千位分隔没了、或者 20 变成了 20.0 的反面，都会让人以为数值变了。

// formatAmount 对应 Python 的 "{:,.2f}"：千位分隔 + 固定两位小数。
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

// formatFloat 对应 Python 的 str(float)：最短可往返的写法，整数值补 ".0"。
//
// 订阅金额在 Python 版是直接拼进文本的，20 写出来就是 "20.0"。
// 不能用 Go 的 %g：它在 100 万以上就换成科学计数法，Python 要到 1e16 才换。
func formatFloat(v float64) string {
	if s, ok := nonFinite(v); ok {
		return s
	}

	sci := strconv.FormatFloat(v, 'e', -1, 64) // 形如 "1.599e+01"
	_, expText, _ := strings.Cut(sci, "e")
	exp, err := strconv.Atoi(expText)
	if err == nil && (exp < -4 || exp >= 16) {
		return sci // 这个区间外 Python 也用科学计数法，且写法与 Go 一致
	}

	s := strconv.FormatFloat(v, 'f', -1, 64)
	if !strings.Contains(s, ".") {
		s += ".0"
	}
	return s
}

// nonFinite 保证 NaN / Inf 也能写成 Python 的样子，而不是 "NaN." 这种半截结果。
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

// isoLocal 对应 Python 的 datetime.now().isoformat()：本地时间、不带时区，
// 微秒为 0 时连小数部分一起省掉。
func isoLocal(t time.Time) string {
	if t.Nanosecond()/1000 == 0 {
		return t.Format("2006-01-02T15:04:05")
	}
	return t.Format("2006-01-02T15:04:05.000000")
}
