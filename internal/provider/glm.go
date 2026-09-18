package provider

import (
	"errors"
	"fmt"
	"math"
)

// Implementation note.
// Implementation note.
// Implementation note.
// Implementation note.
//
// Implementation note.
var glmSpec = Spec{
	Key:         "glm",
	Name:        "GLM",
	DefaultType: "quota",
	URL:         "https://open.bigmodel.cn/api/monitor/usage/quota/limit",
	Headers:     map[string]string{"Accept": "application/json"},
	Check: func(data map[string]any) error {
		if !truthy(data["success"]) || !glmCodeOK(data["code"]) {
			return fmt.Errorf("API returned an error: %s", messageOr(data, "msg", "Unknown error"))
		}
		return nil
	},
	Extract: func(data map[string]any) (float64, error) {
		limits, ok := Dig(data, "data", "limits").([]any)
		if !ok {
			return 0, errors.New("Could not parse data.limits field")
		}

		// Implementation note.
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
			return 0, errors.New("data.limits contains no parseable quota window")
		}
		return round2(lowest), nil
	},
}

// Implementation note.
// Implementation note.
// Implementation note.
func glmCodeOK(code any) bool {
	if code == nil {
		return true
	}
	value, ok := jsonNum(code)
	return ok && value == 200
}

// Implementation note.
// Implementation note.
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
