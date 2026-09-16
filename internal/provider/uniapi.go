package provider

import "errors"

// UniAPI 的余额是美元预付款，unit=usd 是接口要求的显式单位。
var uniapiSpec = Spec{
	Key:         "uniapi",
	Name:        "UniAPI",
	DefaultType: "credits",
	URL:         "https://api.uniapi.io/v1/billing/usage",
	Params:      map[string]string{"unit": "usd"},
	Check: func(data map[string]any) error {
		if !truthy(data["success"]) {
			return errors.New("API 返回 success=false")
		}
		return nil
	},
	Extract: func(data map[string]any) (float64, error) {
		balance, ok := Num(Dig(data, "data", "balance"))
		if !ok {
			return 0, errors.New("无法从响应中解析 balance 字段")
		}
		return balance, nil
	},
}

func init() { RegisterSpec(uniapiSpec) }
