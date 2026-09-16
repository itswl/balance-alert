package provider

import "errors"

// OpenRouter 只给累计充值和累计消费，净余额要自己相减。
var openRouterSpec = Spec{
	Key:         "openrouter",
	Name:        "OpenRouter",
	DefaultType: "credits",
	URL:         "https://openrouter.ai/api/v1/credits",
	Extract: func(data map[string]any) (float64, error) {
		// 两种响应结构都见过：字段包在 data 下，或者直接平铺在顶层
		scope := data
		if nested, ok := data["data"]; ok {
			scope = Object(nested)
		}
		total, ok := Num(scope["total_credits"])
		if !ok {
			return 0, errors.New("无法从响应中解析 total_credits 字段")
		}
		used, ok := Num(scope["total_usage"])
		if !ok {
			return 0, errors.New("无法从响应中解析 total_usage 字段")
		}
		return total - used, nil
	},
}

func init() { RegisterSpec(openRouterSpec) }
