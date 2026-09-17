package provider

import "testing"

// 这些小工具决定了边界数据（0、空串、null、字符串数字）走哪条分支，
// 所以单独钉住，不只靠各平台的用例顺带覆盖。

func TestTruthy(t *testing.T) {
	cases := []struct {
		name string
		in   any
		want bool
	}{
		{"null", nil, false},
		{"false", false, false},
		{"true", true, true},
		{"数字 0", float64(0), false},
		{"数字 1", float64(1), true},
		{"空串", "", false},
		{"非空串", "x", true},
		{"空数组", []any{}, false},
		{"非空数组", []any{1}, true},
		{"空对象", map[string]any{}, false},
		{"非空对象", map[string]any{"a": 1}, true},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			if got := truthy(tc.in); got != tc.want {
				t.Errorf("truthy(%v) = %v，期望 %v", tc.in, got, tc.want)
			}
		})
	}
}

func TestJSONNumRejectsStrings(t *testing.T) {
	// 和 Num 的区别就在这：字符串数字不算数字
	if _, ok := jsonNum("12"); ok {
		t.Error(`jsonNum("12") 不该通过`)
	}
	if _, ok := jsonNum(true); ok {
		t.Error("jsonNum(true) 不该通过")
	}
	if got, ok := jsonNum(float64(12.5)); !ok || got != 12.5 {
		t.Errorf("jsonNum(12.5) = %v, %v", got, ok)
	}
}

func TestOrElse(t *testing.T) {
	// 取第一个真值：a 是假值就取 b，哪怕 b 也是假值
	if got := orElse(nil, float64(5)); got != float64(5) {
		t.Errorf("orElse(nil, 5) = %v", got)
	}
	if got := orElse(float64(0), float64(0)); got != float64(0) {
		t.Errorf("orElse(0, 0) = %v", got)
	}
	if got := orElse(float64(3), float64(9)); got != float64(3) {
		t.Errorf("orElse(3, 9) = %v", got)
	}
}

func TestMessageOr(t *testing.T) {
	data := map[string]any{"msg": "出错了", "empty": "", "code": float64(401)}
	if got := messageOr(data, "msg", "未知错误"); got != "出错了" {
		t.Errorf("msg = %q", got)
	}
	// 键存在但是空串就用空串，只有键不存在才退回默认
	if got := messageOr(data, "empty", "未知错误"); got != "" {
		t.Errorf("empty = %q", got)
	}
	if got := messageOr(data, "missing", "未知错误"); got != "未知错误" {
		t.Errorf("missing = %q", got)
	}
	// 数字要打成 401 而不是 4.01e+02
	if got := messageOr(data, "code", "未知错误"); got != "401" {
		t.Errorf("code = %q", got)
	}
}

func TestFormatValue(t *testing.T) {
	if got := formatValue(map[string]any{"Code": "A&B", "N": float64(1)}); got != `{"Code":"A&B","N":1}` {
		t.Errorf("对象 = %q，& 不该被转义成 \\u0026", got)
	}
	if got := formatValue(float64(1234.5)); got != "1234.5" {
		t.Errorf("小数 = %q", got)
	}
	if got := formatValue("原样"); got != "原样" {
		t.Errorf("字符串 = %q", got)
	}
}

func TestParseJSONObject(t *testing.T) {
	// 空体和 null 都算空响应，由调用方报「API 返回空响应」
	for _, body := range []string{"", "   ", "null"} {
		data, err := parseJSONObject(body)
		if err != nil || len(data) != 0 {
			t.Errorf("parseJSONObject(%q) = %v, %v", body, data, err)
		}
	}

	if _, err := parseJSONObject("<html>"); err == nil ||
		err.Error() != "响应内容不是有效的JSON格式：<html>" {
		t.Errorf("错误 = %v", err)
	}

	data, err := parseJSONObject(`{"a":1}`)
	if err != nil || data["a"] != float64(1) {
		t.Errorf("= %v, %v", data, err)
	}
}
