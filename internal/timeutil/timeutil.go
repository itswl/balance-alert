// Package timeutil 解析定时任务的时刻表达式，并计算下一次触发时间。
//
// 纯函数，不依赖项目内其它包（config 与 scheduler 都要用它，不能有环）。
// 星期一律用 ISO 编号：1=周一 … 7=周日。
package timeutil

import (
	"fmt"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"time"
)

// ClockTime 是一天内的某个时刻。
type ClockTime struct {
	Hour   int
	Minute int
}

func (c ClockTime) String() string { return fmt.Sprintf("%02d:%02d", c.Hour, c.Minute) }

func (c ClockTime) before(other ClockTime) bool {
	return c.Hour < other.Hour || (c.Hour == other.Hour && c.Minute < other.Minute)
}

// 这些值表示"关闭该任务"。
var offValues = map[string]bool{
	"off": true, "none": true, "disabled": true, "false": true, "0": true, "-": true,
}

var timePattern = regexp.MustCompile(`^(\d{1,2}):(\d{2})$`)

// 星期写法，值为 ISO 编号。
var weekdayNames = map[string]int{
	"mon": 1, "monday": 1, "周一": 1, "一": 1,
	"tue": 2, "tues": 2, "tuesday": 2, "周二": 2, "二": 2,
	"wed": 3, "wednesday": 3, "周三": 3, "三": 3,
	"thu": 4, "thur": 4, "thurs": 4, "thursday": 4, "周四": 4, "四": 4,
	"fri": 5, "friday": 5, "周五": 5, "五": 5,
	"sat": 6, "saturday": 6, "周六": 6, "六": 6,
	"sun": 7, "sunday": 7, "周日": 7, "周天": 7, "日": 7, "天": 7,
}

// ParseDailyTimes 把 "09:00,15:30" 解析成去重排序后的时刻列表；off / none 等表示关闭。
// 格式不对时返回错误，配合启动时校验做到配置错就起不来。
func ParseDailyTimes(text string) ([]ClockTime, error) {
	raw := strings.TrimSpace(text)
	if raw == "" || offValues[strings.ToLower(raw)] {
		return nil, nil
	}

	seen := make(map[ClockTime]bool)
	var result []ClockTime
	for _, part := range strings.Split(raw, ",") {
		part = strings.TrimSpace(part)
		if part == "" {
			continue
		}
		matched := timePattern.FindStringSubmatch(part)
		if matched == nil {
			return nil, fmt.Errorf("时刻格式错误: %q，应为 HH:MM，多个时刻用逗号分隔", part)
		}
		hour, _ := strconv.Atoi(matched[1])
		minute, _ := strconv.Atoi(matched[2])
		if hour < 0 || hour > 23 || minute < 0 || minute > 59 {
			return nil, fmt.Errorf("时刻越界: %q", part)
		}
		c := ClockTime{Hour: hour, Minute: minute}
		if !seen[c] {
			seen[c] = true
			result = append(result, c)
		}
	}
	sort.Slice(result, func(i, j int) bool { return result[i].before(result[j]) })
	return result, nil
}

// ParseWeekdays 把 "Mon,Thu" / "周一" 解析成 {1,4}；空表示不限定星期。
func ParseWeekdays(text string) (map[int]bool, error) {
	if strings.TrimSpace(text) == "" {
		return nil, nil
	}
	result := make(map[int]bool)
	for _, part := range strings.Split(strings.ReplaceAll(text, "、", ","), ",") {
		part = strings.ToLower(strings.TrimSpace(part))
		if part == "" {
			continue
		}
		if n, err := strconv.Atoi(part); err == nil {
			if n < 1 || n > 7 {
				return nil, fmt.Errorf("星期格式错误: %q，可写 Mon / 周一 / 1", part)
			}
			result[n] = true
			continue
		}
		day, ok := weekdayNames[part]
		if !ok {
			return nil, fmt.Errorf("星期格式错误: %q，可写 Mon / 周一 / 1", part)
		}
		result[day] = true
	}
	return result, nil
}

// ParseWeeklySchedule 把 "Mon 09:00" 解析成 ({1}, [09:00])；省略星期表示每天，off 表示关闭。
// 星期与时刻之间用空格分隔，各自都能用逗号写多个，例如 "Mon,Thu 09:00,18:00"。
func ParseWeeklySchedule(text string) (map[int]bool, []ClockTime, error) {
	raw := strings.TrimSpace(text)
	if raw == "" || offValues[strings.ToLower(raw)] {
		return nil, nil, nil
	}
	parts := strings.SplitN(raw, " ", 2)
	if len(parts) == 1 {
		times, err := ParseDailyTimes(parts[0])
		return nil, times, err
	}
	weekdays, err := ParseWeekdays(parts[0])
	if err != nil {
		return nil, nil, err
	}
	times, err := ParseDailyTimes(strings.TrimSpace(parts[1]))
	return weekdays, times, err
}

var weekdayLabels = []rune("一二三四五六日")

// Describe 把时刻表渲染成人话，用于自检输出与 /api/jobs。
func Describe(times []ClockTime, weekdays map[int]bool) string {
	if len(times) == 0 {
		return "已关闭"
	}
	clocks := make([]string, len(times))
	for i, t := range times {
		clocks[i] = t.String()
	}
	clock := strings.Join(clocks, " / ")
	if len(weekdays) == 0 {
		return "每天 " + clock
	}
	days := make([]int, 0, len(weekdays))
	for d := range weekdays {
		days = append(days, d)
	}
	sort.Ints(days)
	labels := make([]string, len(days))
	for i, d := range days {
		labels[i] = string(weekdayLabels[d-1])
	}
	return "每周" + strings.Join(labels, "、") + " " + clock
}

// ISOWeekday 返回 1=周一 … 7=周日。
func ISOWeekday(t time.Time) int {
	if w := int(t.Weekday()); w == 0 {
		return 7
	} else {
		return w
	}
}

// NextOccurrence 返回严格晚于 now 的下一个触发时刻。
// weekdays 非空时只在这些星期触发。返回值与 now 同时区。
func NextOccurrence(now time.Time, times []ClockTime, weekdays map[int]bool) (time.Time, bool) {
	if len(times) == 0 {
		return time.Time{}, false
	}
	ordered := append([]ClockTime(nil), times...)
	sort.Slice(ordered, func(i, j int) bool { return ordered[i].before(ordered[j]) })

	for offset := 0; offset < 8; offset++ { // 最多找一周，一定能落到某一天
		day := now.AddDate(0, 0, offset)
		if len(weekdays) > 0 && !weekdays[ISOWeekday(day)] {
			continue
		}
		for _, c := range ordered {
			candidate := time.Date(day.Year(), day.Month(), day.Day(), c.Hour, c.Minute, 0, 0, now.Location())
			if candidate.After(now) {
				return candidate, true
			}
		}
	}
	return time.Time{}, false
}

// UTCISO 把时间转成 Z 结尾的 ISO 字符串，nil 时间返回 nil。
func UTCISO(t time.Time) *string {
	if t.IsZero() {
		return nil
	}
	s := t.UTC().Format("2006-01-02T15:04:05.999999Z")
	return &s
}

// NowISO 是当前时刻的 UTC ISO 字符串。
func NowISO() string { return time.Now().UTC().Format("2006-01-02T15:04:05.999999Z") }
