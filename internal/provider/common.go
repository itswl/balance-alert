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

// 这里放各适配器共用的取值语义：真值判断、带默认值的取字段、"是不是数字" 的判定。
// 它们决定了边界数据（0、空串、null、字符串数字）走哪条分支，
// 集中一处才不会各适配器各写一份、各错一处。

// truthy 判定一个 JSON 值是不是"真"：null / false / 0 / 空串 / 空容器为假，其余为真。
// 平台的 success、code 这类字段类型不统一，同一个语义可能写成 true、1 或非空字符串，
// 直接写 v == true 会在 success: 1 这种响应上判错，所以统一走真值判断。
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

// jsonNum 只认 JSON 里真正的数字，字符串一律不认。
//
// 这个严格是有意的，别"顺手优化"成宽松的 Num：GLM 算配额、wxrank 判 code 都靠它，
// 把字符串 "0"、"50" 当成数字参与运算，算出来的余额是错的，而且看着很正常、没人会发现。
// Num 的宽松解析是给「平台本来就用字符串传数值」的字段准备的，两者不能互换。
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

// orElse 取第一个真值：a 为假值就取 b，哪怕 b 也是假值。
// wxrank 的后备字段就靠它：score 为 0 时要继续看 credits，而不是直接认 0。
func orElse(a, b any) any {
	if truthy(a) {
		return a
	}
	return b
}

// messageOr 取一个字段当错误文案：键存在就用它的值，哪怕值是空串或 null，
// 只有键不存在才退回默认文案。
func messageOr(data map[string]any, key, fallback string) string {
	value, ok := data[key]
	if !ok {
		return fallback
	}
	return formatValue(value)
}

// formatValue 把 JSON 值渲染成错误消息里的一段文本。
// 数字按十进制原样打（float64(200) 打成 "200" 而不是 "2e+02"），
// 对象和数组转成 JSON——错误消息是给人看的，JSON 比 Go 的 %v 可读。
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

// round2 保留两位小数：按十进制格式化再解回来，正中间的值进偶数（四舍六入五成双）。
// 边界值在 glm_test.go 里钉着，改实现前先看那几条。
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

// parseJSONObject 解析响应体。空体与 null 都返回空 map，不在这里报错：
// 「API 返回空响应」是业务层的判断，各适配器的措辞和处理不一样，交给调用方报。
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
