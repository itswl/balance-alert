// Package notify 把一条告警发到群机器人（飞书 / 钉钉 / 企业微信 / 自定义 HTTP）。
//
// 报文结构、消息模板、字段顺序与数字写法都是对外契约：值班群里看惯了这个格式，
// 自定义 webhook 那头还有系统在按字段名取值，改一个字都算回归。
// payload_test.go 与 message_test.go 把它们逐字节钉死了。本包只负责发出去，
// 成功失败的指标由调用方记——同一条消息可能来自余额、跑道、周报等不同场景。
package notify

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"strings"
	"time"
)

// 支持的目标平台。顺序是固定的，配置自检会原样列给用户看。
const (
	TypeFeishu   = "feishu"
	TypeCustom   = "custom"
	TypeDingTalk = "dingtalk"
	TypeWeCom    = "wecom"
)

// 指标分类。余额与订阅走纯文本/结构化报文，其余走富文本卡片，
// Send 就是靠 Kind 区分这两条路的——它们的正文格式本来就不一样。
const (
	KindBalance      = "balance"
	KindSubscription = "subscription"
	KindEmail        = "email"
	KindMailboxError = "mailbox_error"
	KindRunway       = "runway"
	KindSpendSpike   = "spend_spike"
	KindWeeklyReport = "weekly_report"
)

// 重试节奏：总共三次尝试，失败后分别等 2 秒、4 秒。
var defaultBackoff = []time.Duration{2 * time.Second, 4 * time.Second}

// 响应体只读这么多，用于拼错误信息；机器人的错误响应都很短。
const maxResponseBody = 4096

// Message 是一条待发的告警。
//
// Lines 是正文的每一行：富文本告警（跑道、邮件、周报）写成 "**字段**: 值"，
// 余额与订阅用纯文本 "字段: 值"——钉钉那边会自己补上列表和加粗。
type Message struct {
	Title string
	Lines []string
	Kind  string

	// custom 类型的余额/订阅告警发的是结构化信封，里面有 CurrentValue 这类原始数值，
	// 从 Lines 里反解不回来，只能由本包的构造函数顺手带上。外部直接拼 Message 时它是 nil，
	// 退化成通用信封——跑道、周报那些本来就走通用信封，不受影响。
	envelope *envelope
}

// Notifier 发送一条告警。
type Notifier interface {
	Send(ctx context.Context, msg Message) error
}

// SupportedTypes 返回支持的平台列表，顺序固定，配置自检直接拿去提示用户。
func SupportedTypes() []string {
	return []string{TypeFeishu, TypeCustom, TypeDingTalk, TypeWeCom}
}

// New 按配置造一个通知器。
//
// 没配 URL 说明这套部署压根不发告警，返回 nil, nil，调用方据此跳过发送。
// 类型不认识时直接报错，不按 custom 兜底：兜底发出去的是一条谁也解析不了的 JSON，
// 而且要等真出告警那天才会有人发现，还不如起不来的时候就把配置问题说清楚。
func New(url, webhookType, source string, client *http.Client) (Notifier, error) {
	if strings.TrimSpace(url) == "" {
		return nil, nil
	}

	typ := strings.ToLower(strings.TrimSpace(webhookType))
	if typ == "" {
		// 没填类型按 custom 处理；只有真写错了类型名才报错
		typ = TypeCustom
	}
	if !supported(typ) {
		return nil, fmt.Errorf("不支持的 webhook 类型 %q，可选 %s",
			webhookType, strings.Join(SupportedTypes(), "/"))
	}
	if client == nil {
		client = http.DefaultClient
	}

	return &notifier{
		url:     url,
		typ:     typ,
		source:  source,
		client:  client,
		now:     time.Now,
		backoff: defaultBackoff,
	}, nil
}

func supported(typ string) bool {
	for _, t := range SupportedTypes() {
		if t == typ {
			return true
		}
	}
	return false
}

type notifier struct {
	url    string
	typ    string
	source string
	client *http.Client

	now     func() time.Time // 自定义报文里的时间戳；测试要能钉死
	backoff []time.Duration  // 每次重试前的等待，长度即重试次数
}

// Send 发一条告警。失败一律返回错误，不在这里降级——调用方要靠它记指标、决定是否留痕。
func (n *notifier) Send(ctx context.Context, msg Message) error {
	body, err := json.Marshal(n.payload(msg))
	if err != nil {
		return fmt.Errorf("序列化 webhook 报文失败: %w", err)
	}

	log := slog.Default()
	log.Info("准备发送 Webhook", "url", MaskURL(n.url), "type", n.typ, "kind", msg.Kind)
	log.Debug("请求体", "payload", snippet(body, 500))

	var last error
	for attempt := 0; ; attempt++ {
		err := n.post(ctx, body)
		if err == nil {
			return nil
		}
		last = err

		var retry retryError
		if !errors.As(err, &retry) || attempt >= len(n.backoff) {
			return last
		}
		if waitErr := wait(ctx, n.backoff[attempt]); waitErr != nil {
			return fmt.Errorf("%w（重试中断: %v）", last, waitErr)
		}
	}
}

func (n *notifier) post(ctx context.Context, body []byte) error {
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, n.url, bytes.NewReader(body))
	if err != nil {
		return fmt.Errorf("构造 webhook 请求失败: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")

	start := time.Now()
	resp, err := n.client.Do(req)
	if err != nil {
		// 超时、DNS、连接被拒都归这里，等一会儿再发多半能成
		return retryError{fmt.Errorf("请求 webhook 失败: %w", err)}
	}
	defer resp.Body.Close()
	// 读完再关，连接才能还回池子里复用
	text, _ := io.ReadAll(io.LimitReader(resp.Body, maxResponseBody))
	elapsed := time.Since(start)

	switch {
	case resp.StatusCode >= 200 && resp.StatusCode < 300:
		slog.Default().Info("告警发送成功", "type", n.typ, "status", resp.StatusCode, "elapsed", elapsed)
		return nil
	case resp.StatusCode == http.StatusTooManyRequests:
		return retryError{fmt.Errorf("webhook 被限流: HTTP 429, Retry-After: %s, %s",
			resp.Header.Get("Retry-After"), snippet(text, 200))}
	case resp.StatusCode >= 500:
		return retryError{fmt.Errorf("webhook 服务端错误: HTTP %d, %s", resp.StatusCode, snippet(text, 200))}
	default:
		// 4xx 是地址或报文不对，重试多少次都一样
		return fmt.Errorf("webhook 返回 HTTP %d: %s", resp.StatusCode, snippet(text, 500))
	}
}

// retryError 标记"再试一次可能就好了"的失败：超时、连接断开、429 与 5xx。
type retryError struct{ err error }

func (e retryError) Error() string { return e.err.Error() }
func (e retryError) Unwrap() error { return e.err }

// wait 等一段时间，期间 ctx 被取消就立刻回来，别让调度器停在这儿。
func wait(ctx context.Context, d time.Duration) error {
	if d <= 0 {
		return ctx.Err()
	}
	timer := time.NewTimer(d)
	defer timer.Stop()
	select {
	case <-timer.C:
		return nil
	case <-ctx.Done():
		return ctx.Err()
	}
}

// MaskURL 把 webhook 地址里的密钥打码后再写日志。
//
// 按 hook/ → access_token= → key= 的顺序取第一个命中的标记，保留密钥前 4 位。
// provider.MaskURL 是另一套规则（只认路径里的段），这里不复用也不 import：
// notify 被 provider 的上层用着，反向依赖会绕回来。
func MaskURL(raw string) string {
	if raw == "" {
		return ""
	}

	for _, marker := range []string{"hook/", "access_token=", "key="} {
		prefix, secret, found := strings.Cut(raw, marker)
		if !found {
			continue
		}
		if secret == "" {
			return prefix + marker + "***"
		}
		return prefix + marker + head(secret, 4) + "***"
	}

	// 认不出密钥位置时整体打码，短地址干脆全遮
	runes := []rune(raw)
	if len(runes) <= 16 {
		return "***"
	}
	return string(runes[:12]) + "***" + string(runes[len(runes)-4:])
}

func head(s string, n int) string {
	runes := []rune(s)
	if len(runes) <= n {
		return s
	}
	return string(runes[:n])
}

// snippet 按字符（而不是字节）截断，免得把中文错误信息切成半个字。
func snippet(b []byte, limit int) string {
	return head(strings.TrimSpace(string(b)), limit)
}
