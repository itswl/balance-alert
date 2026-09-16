package provider

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strconv"
	"strings"
)

// 这里放移植 Python 版时要保持一致的小语义：真值判断、dict.get 的默认值、
// "是不是数字" 的判定。它们决定了边界数据（0、空串、null、字符串数字）走哪条分支，
// 集中一处才不会各适配器各写一份、各错一处。

// truthy 复刻 Python 的真值判断：None / false / 0 / 空串 / 空容器为假。
// 平台返回 success 或 code 这类字段时，Python 用的是真值而不是相等判断，
// 直接写 v == true 会在 success: 1 这种响应上判错。
func truthy(v any) bool {
	switch value := v.(type) {
	case nil:
		return false
	case bool:
		return value
	case float64:
		return value != 0
	case int:
		return value != 0
	case json.Number:
		f, err := value.Float64()
		return err == nil && f != 0
	case string:
		return value != ""
	case []any:
		return len(value) > 0
	case map[string]any:
		return len(value) > 0
	}
	return true
}

// jsonNum 只认 JSON 里的数字，不认字符串。
// 对应 Python 的 isinstance(x, (int, float))：GLM 算配额、wxrank 判 code 都靠它，
// 这些地方把 "0" 当成数字 0 会算出错误的余额，所以不能用宽松的 Num。
func jsonNum(v any) (float64, bool) {
	switch value := v.(type) {
	case float64:
		return value, true
	case int:
		return float64(value), true
	case json.Number:
		f, err := value.Float64()
		return f, err == nil
	}
	return 0, false
}

// orElse 复刻 Python 的 `a or b`：a 为假值就取 b，哪怕 b 也是假值。
func orElse(a, b any) any {
	if truthy(a) {
		return a
	}
	return b
}

// messageOr 复刻 Python 的 dict.get(key, fallback)：键存在就用它的值，
// 哪怕值是空串或 null——只有键不存在才退回默认文案。
func messageOr(data map[string]any, key, fallback string) string {
	value, ok := data[key]
	if !ok {
		return fallback
	}
	return formatValue(value)
}

// formatValue 把 JSON 值渲染成错误消息里的一段文本。
// 数字按十进制原样打（float64(200) 打成 "200" 而不是 "2e+02"），
// 对象和数组转成 JSON——Python 打的是 dict 字面量，Go 没有等价写法，JSON 最接近且可读。
func formatValue(v any) string {
	switch value := v.(type) {
	case string:
		return value
	case float64:
		return strconv.FormatFloat(value, 'f', -1, 64)
	case int:
		return strconv.Itoa(value)
	}
	var buf bytes.Buffer
	enc := json.NewEncoder(&buf)
	enc.SetEscapeHTML(false) // 错误消息是给人看的，别把 & < > 变成 & 这种转义
	if err := enc.Encode(v); err != nil {
		return fmt.Sprint(v)
	}
	return strings.TrimRight(buf.String(), "\n")
}

// round2 保留两位小数，用十进制格式化再解回来，
// 与 Python round(x, 2) 的「四舍六入五成双」一致（Go 的 strconv 在正中间时同样进偶数）。
func round2(v float64) float64 {
	rounded, err := strconv.ParseFloat(strconv.FormatFloat(v, 'f', 2, 64), 64)
	if err != nil {
		return v
	}
	return rounded
}

// percentEncode 是 RFC 3986 的百分号编码：只有字母、数字和 -_.~ 原样保留。
// 火山与阿里云的签名都要求这个编码，和 url.QueryEscape 的差别在空格（%20 而不是 +）
// 和 ~（不编码）；签名对一个字节都不能差，所以自己实现，不依赖标准库的取舍。
func percentEncode(s string) string {
	var b strings.Builder
	b.Grow(len(s))
	for i := 0; i < len(s); i++ {
		c := s[i]
		switch {
		case 'a' <= c && c <= 'z', 'A' <= c && c <= 'Z', '0' <= c && c <= '9',
			c == '-', c == '_', c == '.', c == '~':
			b.WriteByte(c)
		default:
			fmt.Fprintf(&b, "%%%02X", c)
		}
	}
	return b.String()
}

// fetchBody 发请求并读回响应体。火山与阿里云对状态码的处理不一样
// （火山非 200 直接算失败，阿里云的业务错误就是用 4xx + JSON 返回的），
// 所以这里只管取回来，判状态码留给各自的适配器。
func fetchBody(client *Client, req *http.Request) (int, string, error) {
	resp, err := client.Do(req)
	if err != nil {
		return 0, "", err
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(io.LimitReader(resp.Body, 4<<20))
	if err != nil {
		return resp.StatusCode, "", fmt.Errorf("读取响应失败: %w", err)
	}
	return resp.StatusCode, string(body), nil
}

// parseJSONObject 解析响应体。空体与 null 都返回空 map，
// 由调用方报「API 返回空响应」——Python 版就是这么分的层。
func parseJSONObject(body string) (map[string]any, error) {
	if strings.TrimSpace(body) == "" {
		return nil, nil
	}
	var data map[string]any
	if err := json.Unmarshal([]byte(body), &data); err != nil {
		return nil, fmt.Errorf("响应内容不是有效的JSON格式：%s", body)
	}
	return data, nil
}
