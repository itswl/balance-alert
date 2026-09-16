// Package runway 从余额快照里还原消耗速率，算出"还能用几天"。
//
// 余额历史是一串快照，相邻两点之间余额下降就是消耗，上升就是充值。据此能算出日均消耗、
// 跑道（按当前速率还能用几天），以及今天的消耗是不是比平时突然放大了。这两件事比静态阈值
// 更早也更准：同样是 430 元，日烧 5 元和日烧 200 元完全是两回事。
//
// 没有数据库就没有历史，所有结果为空，调用方自然退回到纯阈值告警。
package runway

import (
	"math"
	"sort"
	"time"

	"github.com/itswl/balance-alert/internal/model"
)

// 少于这些数据就不下结论：算出来的速率没有意义。
const (
	MinPoints      = 4
	MinSpanHours   = 6.0
	MinBaselineDay = 3 // 突增判断至少要有几个完整的历史日做基线
)

type point struct {
	at      time.Time
	balance float64
}

// Compute 从一个账户的余额快照序列算出消耗画像。
//
// records 必须按时间升序；账户信息取最后一条。now 传零值时用当前时间。
func Compute(records []model.BalancePoint, windowDays int, now time.Time) model.Runway {
	if now.IsZero() {
		now = time.Now()
	}
	points := validPoints(records)

	result := model.Runway{
		WindowDays: windowDays,
		DataPoints: len(points),
		Confidence: model.ConfidenceNone,
		Daily:      []model.DailySpend{},
	}
	if n := len(records); n > 0 {
		last := records[n-1]
		result.ProjectID = last.ProjectID
		result.ProjectName = last.ProjectName
		result.Provider = last.Provider
		result.BalanceType = last.BalanceType
	}
	if len(points) > 0 {
		result.CurrentBalance = model.Ptr(points[len(points)-1].balance)
	}
	if len(points) < 2 {
		return result
	}

	span := points[len(points)-1].at.Sub(points[0].at)
	result.SpanHours = round(span.Hours(), 2)

	consumed, toppedUp, perDay := splitFlows(points)
	result.Consumed, result.ToppedUp = consumed, toppedUp
	result.Confidence = confidence(len(points), result.SpanHours)
	if result.Confidence == model.ConfidenceNone {
		return result
	}

	// 除数下限取一小时，防止极短窗口把速率放大到离谱
	burn := round(result.Consumed/math.Max(result.SpanHours/24, 1.0/24), 4)
	result.BurnPerDay = &burn
	if burn > 0 && result.CurrentBalance != nil {
		days := round(math.Max(*result.CurrentBalance, 0)/burn, 2)
		result.RunwayDays = &days
		depletion := now.Add(time.Duration(days * float64(24*time.Hour))).Format("2006-01-02")
		result.DepletionDate = &depletion
	}

	result.Daily = fillDaily(perDay, points[0].at, points[len(points)-1].at)
	result.TodayConsumed, result.BaselineSpend, result.SpikeRatio = spike(result.Daily, now.Format("2006-01-02"))
	return result
}

// validPoints 丢掉解析不出时间或余额的记录，并按时间升序。
// 数据库里存的是 UTC，这里转成本地时间，因为"今天消耗了多少"要按用户所在时区分天。
func validPoints(records []model.BalancePoint) []point {
	points := make([]point, 0, len(records))
	for _, r := range records {
		if r.Timestamp == 0 {
			continue
		}
		points = append(points, point{at: time.Unix(r.Timestamp, 0).Local(), balance: r.Balance})
	}
	sort.Slice(points, func(i, j int) bool { return points[i].at.Before(points[j].at) })
	return points
}

// splitFlows 把余额序列还原成收支：下降是消耗，上升是充值；消耗同时按本地日期归集。
func splitFlows(points []point) (consumed, toppedUp float64, perDay map[string]float64) {
	perDay = make(map[string]float64)
	for i := 1; i < len(points); i++ {
		delta := points[i-1].balance - points[i].balance
		switch {
		case delta > 0:
			consumed += delta
			day := points[i].at.Format("2006-01-02")
			perDay[day] += delta
		case delta < 0:
			toppedUp += -delta
		}
	}
	return round(consumed, 4), round(toppedUp, 4), perDay
}

// fillDaily 按日铺平，没有消耗的日子补 0，这样中位数才反映真实的"平时"。
func fillDaily(perDay map[string]float64, start, end time.Time) []model.DailySpend {
	startDay := time.Date(start.Year(), start.Month(), start.Day(), 0, 0, 0, 0, start.Location())
	endDay := time.Date(end.Year(), end.Month(), end.Day(), 0, 0, 0, 0, end.Location())

	var daily []model.DailySpend
	for day := startDay; !day.After(endDay); day = day.AddDate(0, 0, 1) {
		key := day.Format("2006-01-02")
		daily = append(daily, model.DailySpend{Date: key, Consumed: round(perDay[key], 4)})
	}
	return daily
}

// spike 算今日消耗与日常水平的倍数。最后一天不是今天、或基线不足时后两项为 nil。
func spike(daily []model.DailySpend, today string) (todayConsumed, baseline, ratio *float64) {
	if len(daily) == 0 || daily[len(daily)-1].Date != today {
		return nil, nil, nil
	}
	consumed := daily[len(daily)-1].Consumed
	todayConsumed = &consumed

	history := daily[:len(daily)-1]
	if len(history) < MinBaselineDay {
		return todayConsumed, nil, nil
	}
	values := make([]float64, len(history))
	for i, d := range history {
		values[i] = d.Consumed
	}
	mid := round(median(values), 4)
	baseline = &mid
	if mid > 0 {
		r := round(consumed/mid, 2)
		ratio = &r
	}
	return todayConsumed, baseline, ratio
}

// confidence 数据太少或跨度太短就不下结论；跨度不足一天的结果不用于告警。
func confidence(points int, spanHours float64) string {
	switch {
	case points < MinPoints || spanHours < MinSpanHours:
		return model.ConfidenceNone
	case spanHours < 24:
		return model.ConfidenceLow
	case spanHours < 72:
		return model.ConfidenceMedium
	default:
		return model.ConfidenceHigh
	}
}

// ComputeAll 把一批快照按账户分组，各算一份画像。
func ComputeAll(series []model.BalancePoint, windowDays int, now time.Time) map[string]model.Runway {
	if len(series) == 0 {
		return nil
	}
	byProject := make(map[string][]model.BalancePoint)
	for _, r := range series {
		byProject[r.ProjectID] = append(byProject[r.ProjectID], r)
	}
	out := make(map[string]model.Runway, len(byProject))
	for id, records := range byProject {
		out[id] = Compute(records, windowDays, now)
	}
	return out
}

// Attach 把画像挂到余额检查结果上，供看板、指标和告警共用。
func Attach(results []model.CheckResult, runways map[string]model.Runway) {
	if len(runways) == 0 {
		return
	}
	for i := range results {
		if !results[i].Success {
			continue
		}
		if r, ok := runways[model.ProjectID(results[i].Provider, results[i].Project)]; ok {
			results[i].Runway = &r
		}
	}
}

func median(values []float64) float64 {
	sorted := append([]float64(nil), values...)
	sort.Float64s(sorted)
	n := len(sorted)
	if n == 0 {
		return 0
	}
	if n%2 == 1 {
		return sorted[n/2]
	}
	return (sorted[n/2-1] + sorted[n/2]) / 2
}

// round 保留 n 位小数，用银行家舍入（四舍六入五成双）。
//
// 必须和 Python 的 round() 一致：2.125 要进成 2.12 而不是 2.13。差这 0.01 平时无所谓，
// 但跑道天数正好压在告警阈值上时会决定发不发告警，迁移前后的看板数字也会对不上。
func round(value float64, decimals int) float64 {
	shift := math.Pow(10, float64(decimals))
	return math.RoundToEven(value*shift) / shift
}
