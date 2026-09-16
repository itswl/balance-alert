package provider

import "errors"

// DeepSeek 一个账号可能有多币种子账户，余额取人民币账户的总额。
var deepseekSpec = Spec{
	Key:         "deepseek",
	Name:        "DeepSeek",
	DefaultType: "balance",
	URL:         "https://api.deepseek.com/user/balance",
	Headers:     map[string]string{"Accept": "application/json"},
	Extract: func(data map[string]any) (float64, error) {
		infos, ok := data["balance_infos"].([]any)
		if !ok || len(infos) == 0 {
			return 0, errors.New("无法从响应中解析 balance_infos 字段")
		}

		// 优先人民币账户，没有就退回第一条
		chosen := Object(infos[0])
		for _, item := range infos {
			if obj := Object(item); obj != nil && Str(obj["currency"]) == "CNY" {
				chosen = obj
				break
			}
		}

		// 线上这个字段是字符串金额（"430.37"）
		total, ok := Num(chosen["total_balance"])
		if !ok {
			return 0, errors.New("无法从响应中解析 total_balance 字段")
		}
		return total, nil
	},
}

func init() { RegisterSpec(deepseekSpec) }
