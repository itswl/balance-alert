package provider

import "errors"

// Implementation note.
var tikhubSpec = Spec{
	Key:         "tikhub",
	Name:        "TikHub",
	DefaultType: "balance",
	URL:         "https://api.tikhub.dev/api/v1/tikhub/user/get_user_info",
	Headers:     map[string]string{"accept": "application/json"},
	Extract: func(data map[string]any) (float64, error) {
		// Implementation note.
		scope := data
		if v, ok := data["user_data"]; ok {
			scope = Object(v)
		} else if v, ok := data["data"]; ok {
			scope = Object(v)
		}
		balance, ok := Num(scope["balance"])
		if !ok {
			return 0, errors.New("Could not parse balance field")
		}
		return balance, nil
	},
}

func init() { RegisterSpec(tikhubSpec) }
