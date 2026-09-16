// Package subscription 管订阅续费提醒：算出距离下次续费还有几天，该提醒就提醒。
//
// 这个包几乎全是日期边界：2 月 29 日的年付在平年该落到哪天、31 号的月付在 2 月该落到哪天、
// 本月的续费日到底过没过。这些地方错一天，用户就会在续费当天收不到提醒。
package subscription

import (
	"regexp"
	"strconv"
	"strings"
	"time"
)

// SplitMMDD 把年付的 MMDD 整数（如 315）拆成月和日；不是合法 MMDD 时返回 false。
//
// 小于等于 31 的值属于旧配置的"只写了日"，不是 MMDD。
func SplitMMDD(renewalDay int) (month, day int, ok bool) {
	if renewalDay <= 31 {
		return 0, 0, false
	}
	month, day = renewalDay/100, renewalDay%100
	if month >= 1 && month <= 12 && day >= 1 && day <= 31 {
		return month, day, true
	}
	return 0, 0, false
}

var mmddPattern = regexp.MustCompile(`^(\d{1,2})\s*[-/月]\s*(\d{1,2})\s*日?$`)

// CoerceRenewalDay 归一化续费日。
//
// 年付支持直观的 "03-15" / "3-15" 写法，内部统一存成 MMDD 整数（315）；
// 周付月付接受数字或数字字符串。解析不出来时返回 false，由调用方报参数错误。
func CoerceRenewalDay(value string, cycleType string) (int, bool) {
	text := strings.TrimSpace(value)
	if matched := mmddPattern.FindStringSubmatch(text); matched != nil {
		month, _ := strconv.Atoi(matched[1])
		day, _ := strconv.Atoi(matched[2])
		if cycleType == "yearly" {
			return month*100 + day, true
		}
		return day, true
	}
	if n, err := strconv.Atoi(text); err == nil {
		return n, true
	}
	return 0, false
}

// safeMonthDate 构造月内日期，目标日超出当月天数时回退到月末。
// 31 号的月付在 2 月要落到 28 或 29 号，而不是溢出到 3 月。
func safeMonthDate(year int, month time.Month, day int, loc *time.Location) time.Time {
	maxDay := daysInMonth(year, month)
	if day > maxDay {
		day = maxDay
	}
	if day < 1 {
		day = 1
	}
	return time.Date(year, month, day, 0, 0, 0, 0, loc)
}

func daysInMonth(year int, month time.Month) int {
	// 下个月的第 0 天就是本月最后一天
	return time.Date(year, month+1, 0, 0, 0, 0, 0, time.UTC).Day()
}

// shiftMonth 在给定日期的月份上偏移 months 个月，取该月的 day（超出则回退月末）。
func shiftMonth(base time.Time, months int, day int) time.Time {
	total := int(base.Month()) - 1 + months
	year := base.Year() + floorDiv(total, 12)
	month := time.Month(floorMod(total, 12) + 1)
	return safeMonthDate(year, month, day, base.Location())
}

// safeReplaceYear 换年份，闰年 2 月 29 日在平年回退到 2 月 28 日。
func safeReplaceYear(base time.Time, year int) time.Time {
	return safeMonthDate(year, base.Month(), base.Day(), base.Location())
}

// Go 的 / 和 % 对负数是向零取整，这里要的是向下取整，否则往前推月份会错一个月。
func floorDiv(a, b int) int {
	quotient := a / b
	if (a%b != 0) && ((a < 0) != (b < 0)) {
		quotient--
	}
	return quotient
}

func floorMod(a, b int) int { return a - floorDiv(a, b)*b }

// startOfDay 把时刻截到当天零点。
// 续费日一律是 00:00，不截的话续费当天会算成 -1 天而漏掉提醒。
func startOfDay(t time.Time) time.Time {
	return time.Date(t.Year(), t.Month(), t.Day(), 0, 0, 0, 0, t.Location())
}

// NextRenewal 算出下次续费日期与距今天数。
//
// cycleType 为 weekly 时 renewalDay 是 1-7（周一到周日），monthly 是 1-31，
// yearly 是 MMDD；lastRenewed 非空时年付按上次续费日逐年推。
func NextRenewal(cycleType string, renewalDay int, today time.Time, lastRenewed *time.Time) (days int, next time.Time) {
	today = startOfDay(today)

	switch cycleType {
	case "weekly":
		ahead := renewalDay - isoWeekday(today)
		if ahead < 0 { // 本周已过，看下周
			ahead += 7
		}
		next = today.AddDate(0, 0, ahead)
	case "yearly":
		next = nextYearlyDate(renewalDay, today, lastRenewed)
	default: // monthly：本月的续费日还没过就用本月，否则下个月
		months := 0
		if today.Day() > renewalDay {
			months = 1
		}
		next = shiftMonth(today, months, renewalDay)
	}
	return int(next.Sub(today).Hours() / 24), next
}

// nextYearlyDate 年付的下次续费日：优先按上次续费日推年，否则按 MMDD 取今年或明年。
func nextYearlyDate(renewalDay int, today time.Time, lastRenewed *time.Time) time.Time {
	if lastRenewed != nil {
		// 从上次续费日逐年推进到今天之后，上限 20 年防脏数据死循环
		candidate := safeReplaceYear(*lastRenewed, lastRenewed.Year()+1)
		for range 20 {
			if candidate.After(today) {
				return candidate
			}
			candidate = safeReplaceYear(candidate, candidate.Year()+1)
		}
	}

	month, day, ok := SplitMMDD(renewalDay)
	if !ok {
		// 兼容旧配置：年付但只写了 1-31（或非法值）时，用明年今天
		return safeReplaceYear(today, today.Year()+1)
	}
	// 用 safeMonthDate 而非直接构造：2 月 29 日的订阅在平年要落到 2 月 28 日
	candidate := safeMonthDate(today.Year(), time.Month(month), day, today.Location())
	if !candidate.Before(today) {
		return candidate
	}
	return safeMonthDate(today.Year()+1, time.Month(month), day, today.Location())
}

// cycleStart 是当前续费周期的起始日期，用来判断上次续费落在哪个周期里。
func cycleStart(cycleType string, renewalDay int, today, next time.Time) time.Time {
	switch cycleType {
	case "weekly":
		return next.AddDate(0, 0, -7)
	case "yearly":
		return safeReplaceYear(next, next.Year()-1)
	default: // monthly：本月续费日还没到就算上个月的周期
		months := 0
		if today.Day() < renewalDay {
			months = -1
		}
		return shiftMonth(today, months, renewalDay)
	}
}

func isoWeekday(t time.Time) int {
	if w := int(t.Weekday()); w == 0 {
		return 7
	} else {
		return w
	}
}
