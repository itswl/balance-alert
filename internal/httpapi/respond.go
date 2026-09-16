// Package httpapi 提供看板页面与 /api/* 接口。
//
// 响应契约见 docs/API.md，不许变：已经有前端、脚本和监控在用。
// 出错一律 {"status":"error","message":"..."}，参数校验失败再带一个 errors 数组。
package httpapi

import (
	"crypto/md5"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"net/http"
	"strconv"
	"sync"
	"time"
)

// errorBody 是所有错误响应的统一形状。
type errorBody struct {
	Status  string   `json:"status"`
	Message string   `json:"message,omitempty"`
	Errors  []string `json:"errors,omitempty"`
}

func writeJSON(w http.ResponseWriter, status int, payload any) {
	body, err := json.Marshal(payload)
	if err != nil {
		w.Header().Set("Content-Type", "application/json; charset=utf-8")
		w.WriteHeader(http.StatusInternalServerError)
		_, _ = w.Write([]byte(`{"status":"error","message":"响应序列化失败"}`))
		return
	}
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	_, _ = w.Write(body)
}

func fail(w http.ResponseWriter, status int, message string) {
	writeJSON(w, status, errorBody{Status: "error", Message: message})
}

func failValidation(w http.ResponseWriter, problems []string) {
	writeJSON(w, http.StatusBadRequest, errorBody{Status: "error", Errors: problems})
}

// ok 是成功响应的通用形状：固定带 status=success，其余字段由调用方给。
func ok(w http.ResponseWriter, fields map[string]any) {
	payload := make(map[string]any, len(fields)+1)
	payload["status"] = "success"
	for k, v := range fields {
		payload[k] = v
	}
	writeJSON(w, http.StatusOK, payload)
}

// etagJSON 给读接口加 ETag，前端轮询时命中就只回 304，省掉一整个响应体。
func etagJSON(w http.ResponseWriter, r *http.Request, payload any) {
	body, err := json.Marshal(payload)
	if err != nil {
		fail(w, http.StatusInternalServerError, "响应序列化失败")
		return
	}
	sum := md5.Sum(body)
	etag := hex.EncodeToString(sum[:])

	if r.Header.Get("If-None-Match") == etag {
		w.WriteHeader(http.StatusNotModified)
		return
	}
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.Header().Set("ETag", etag)
	w.Header().Set("Cache-Control", "private, must-revalidate")
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write(body)
}

// decodeJSON 读请求体；不是合法 JSON 时回 400。
func decodeJSON(w http.ResponseWriter, r *http.Request, target any) bool {
	if r.Body == nil {
		fail(w, http.StatusBadRequest, "请求体必须是有效的 JSON")
		return false
	}
	decoder := json.NewDecoder(http.MaxBytesReader(w, r.Body, 1<<20))
	if err := decoder.Decode(target); err != nil {
		fail(w, http.StatusBadRequest, "请求体必须是有效的 JSON")
		return false
	}
	return true
}

// intParam 读查询参数并做范围校验，越界回 400。
func intParam(r *http.Request, name string, fallback, minValue, maxValue int) (int, error) {
	raw := r.URL.Query().Get(name)
	if raw == "" {
		return fallback, nil
	}
	value, err := strconv.Atoi(raw)
	if err != nil {
		return 0, fmt.Errorf("参数错误: %s 必须是整数", name)
	}
	if value < minValue || value > maxValue {
		return 0, fmt.Errorf("参数错误: %s 必须在 %d-%d 之间", name, minValue, maxValue)
	}
	return value, nil
}

// cooldown 是重操作的并发互斥加完成后冷却：同一时间只跑一个，跑完若干秒内不再接受。
//
// 手动刷新和立即扫描都会真的去打上游接口，没有这层护栏，页面上连点几下
// 就能把配额打光，或者把自己的 IP 打进对方的限流名单。
type cooldown struct {
	seconds  int
	mu       sync.Mutex
	busy     bool
	lastDone time.Time
}

// acquire 拿到返回空字符串；拿不到返回给用户看的原因。
func (c *cooldown) acquire() string {
	c.mu.Lock()
	defer c.mu.Unlock()

	if c.busy {
		return "正在进行中，请稍候"
	}
	if remaining := time.Duration(c.seconds)*time.Second - time.Since(c.lastDone); remaining > 0 {
		return fmt.Sprintf("过于频繁，请%d秒后重试", max(1, int(remaining.Seconds())))
	}
	c.busy = true
	return ""
}

func (c *cooldown) release() {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.busy = false
	c.lastDone = time.Now()
}

// maskSecret 给展示用的密钥打码。
func maskSecret(value string, prefix, suffix int) string {
	if value == "" {
		return ""
	}
	if len(value) <= prefix+suffix {
		return "***"
	}
	return value[:prefix] + "***" + value[len(value)-suffix:]
}
