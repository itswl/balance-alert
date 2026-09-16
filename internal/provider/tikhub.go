package provider

import "errors"

// TikHub 返回的是账户余额（美元）。
var tikhubSpec = Spec{
	Key:         "tikhub",
	Name:        "TikHub",
	DefaultType: "balance",
	URL:         "https://api.tikhub.dev/api/v1/tikhub/user/get_user_info",
	Headers:     map[string]string{"accept": "application/json"},
	Extract: func(data map[string]any) (float64, error) {
		// 接口改过版：balance 可能在 user_data 下、data 下或顶层，按这个优先级找
		scope := data
		if v, ok := data["user_data"]; ok {
			scope = Object(v)
		} else if v, ok := data["data"]; ok {
			scope = Object(v)
		}
		balance, ok := Num(scope["balance"])
		if !ok {
			return 0, errors.New("无法从响应中解析 balance 字段")
		}
		return balance, nil
	},
}

func init() { RegisterSpec(tikhubSpec) }
