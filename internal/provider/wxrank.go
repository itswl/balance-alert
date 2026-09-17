package provider

import (
	"fmt"
	"regexp"
	"strconv"
)

// 微信排名没有专门的余额接口，剩余点数写在查询接口的 msg 文本里，如 "剩余263419余额"。
var wxrankDigits = regexp.MustCompile(`\d+`)

var wxrankSpec = Spec{
	Key:         "wxrank",
	Name:        "WxRank",
	DefaultType: "credits",
	URL:         "https://data.wxrank.com/weixin/score",
	Auth:        AuthQuery,
	AuthParam:   "key",
	Check: func(data map[string]any) error {
		code, ok := jsonNum(data["code"])
		if !ok || code != 0 {
			return fmt.Errorf("API 返回错误: %s", messageOr(data, "msg", "未知错误"))
		}
		return nil
	},
	Extract: func(data map[string]any) (float64, error) {
		// 先抠 msg 里的第一串数字
		msg := Str(data["msg"])
		if matched := wxrankDigits.FindString(msg); matched != "" {
			if value, err := strconv.ParseFloat(matched, 64); err == nil {
				return value, nil
			}
		}

		// msg 里没有数字时的后备字段，按这个顺序找：data 本身是数字 > data.score/credits > 顶层 score/credits
		switch raw := data["data"].(type) {
		case float64:
			return raw, nil
		case map[string]any:
			if value, ok := Num(orElse(raw["score"], raw["credits"])); ok {
				return value, nil
			}
		}
		if value, ok := Num(orElse(data["score"], data["credits"])); ok {
			return value, nil
		}
		return 0, fmt.Errorf("无法从响应中解析余额: %s", msg)
	},
}

func init() { RegisterSpec(wxrankSpec) }
