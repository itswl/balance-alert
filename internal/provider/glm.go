package provider

import (
	"errors"
	"fmt"
	"math"
)

// 智谱开放平台没有公开的预付费余额接口，这里查的是 Coding Plan 套餐配额。
// 接口按时间窗口返回若干条限额（5 小时 / 周 / 月，类型有 TOKENS_LIMIT / TIME_LIMIT /
// CREDIT_LIMIT 几种），这里取「剩余比例最低」的那个窗口作为余额，单位是百分比：
// 100 表示一点没用，0 表示用光。阈值也按百分比填，例如 10 表示剩余不足 10% 时告警。
//
// Z.ai 国际站是同一套接口，host 换成 https://api.z.ai 即可。
var glmSpec = Spec{
	Key:         "glm",
	Name:        "GLM",
	DefaultType: "quota",
	URL:         "https://open.bigmodel.cn/api/monitor/usage/quota/limit",
	Headers:     map[string]string{"Accept": "application/json"},
	Check: func(data map[string]any) error {
		if !truthy(data["success"]) || !glmCodeOK(data["code"]) {
			return fmt.Errorf("API 返回错误: %s", messageOr(data, "msg", "未知错误"))
		}
		return nil
	},
	Extract: func(data map[string]any) (float64, error) {
		limits, ok := Dig(data, "data", "limits").([]any)
		if !ok {
			return 0, errors.New("无法从响应中解析 data.limits 字段")
		}

		// 多个窗口同时限流，最紧的那个决定还能不能用，所以取最小值
		lowest := math.Inf(1)
		for _, item := range limits {
			limit := Object(item)
			if limit == nil {
				continue
			}
			if percent, ok := glmRemainingPercent(limit); ok && percent < lowest {
				lowest = percent
			}
		}
		if math.IsInf(lowest, 1) {
			return 0, errors.New("data.limits 里没有可解析的配额窗口")
		}
		return round2(lowest), nil
	},
}

// glmCodeOK 判业务状态码。没有 code 字段视为成功（老接口不返回），
// 有就必须是数字 200：这里走 jsonNum 而不是 Num，字符串 "200" 不算通过——
// 理由见 jsonNum 的说明，放宽会让配额算歪。
func glmCodeOK(code any) bool {
	if code == nil {
		return true
	}
	value, ok := jsonNum(code)
	return ok && value == 200
}

// glmRemainingPercent 算单个窗口的剩余比例。有总量和剩余量就精确算，
// 否则用接口给的已用百分比反推。异常数据钳在 0-100，免得算出负余额或超过满额。
func glmRemainingPercent(limit map[string]any) (float64, bool) {
	usage, hasUsage := jsonNum(limit["usage"])
	remaining, hasRemaining := jsonNum(limit["remaining"])
	if hasUsage && usage > 0 && hasRemaining {
		return clampPercent(remaining / usage * 100), true
	}
	if percentage, ok := jsonNum(limit["percentage"]); ok {
		return clampPercent(100 - percentage), true
	}
	return 0, false
}

func clampPercent(v float64) float64 {
	return math.Max(0, math.Min(100, v))
}

func init() { RegisterSpec(glmSpec) }
