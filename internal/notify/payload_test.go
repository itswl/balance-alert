package notify

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

// 下面每一段期望报文都是 Python 版 services/webhook_adapter.py 实跑导出的
// （json.dumps(..., ensure_ascii=False, separators=(',', ':'))），与 Go 的
// encoding/json 输出可以逐字节比。改动本包时它们只有一个作用：拦住"顺手优化"的格式改动。

// 自定义报文里带时间戳，钉死时钟才能逐字节比对。
var pinnedNow = time.Date(2026, 9, 16, 23, 50, 26, 26504000, time.Local)

type payloadCase struct {
	name string
	msg  Message
	want map[string]string // webhook 类型 -> 期望报文
}

func payloadCases() []payloadCase {
	owner := "核心业务"
	rich := []string{
		"**账户**: TestProject",
		"**所属项目**: 核心业务",
		"**服务商**: OpenRouter",
		"**当前余额**: 1,234.50",
		"**日均消耗**: 120.00（最近 7 天）",
	}

	return []payloadCase{
		{
			name: "余额告警_带所属项目与货币符号",
			msg:  balanceAlert("TestProject", &owner, "OpenRouter", "余额", 1234.5, 10000.0, "¥"),
			want: map[string]string{
				TypeFeishu:   `{"msg_type":"text","content":{"text":"【余额告警】\n\nAPI 调用: TestProject\n所属项目: 核心业务\n服务商: OpenRouter\n当前余额: ¥1,234.50\n告警阈值: ¥10,000.00\n状态: ⚠️ 余额不足\n来源: credit-monitor"}}`,
				TypeDingTalk: `{"msgtype":"markdown","markdown":{"title":"余额告警","text":"## 余额告警\n\n- **API 调用**: TestProject\n- **所属项目**: 核心业务\n- **服务商**: OpenRouter\n- **当前余额**: ¥1,234.50\n- **告警阈值**: ¥10,000.00\n- **状态**: ⚠️ 余额不足"}}`,
				TypeWeCom:    `{"msgtype":"text","text":{"content":"【余额告警】\nAPI 调用: TestProject\n所属项目: 核心业务\n服务商: OpenRouter\n当前余额: ¥1,234.50\n告警阈值: ¥10,000.00\n状态: ⚠️ 余额不足"}}`,
				TypeCustom:   `{"Type":"AlarmNotification","RuleName":"TestProject余额告警","Level":"critical","Resources":[{"ProjectName":"TestProject","OwnerProject":"核心业务","Provider":"OpenRouter","BalanceType":"余额","CurrentValue":1234.5,"Threshold":10000.0,"Unit":"¥","Message":"项目 [TestProject] 余额不足，当前: ¥1,234.50，阈值: ¥10,000.00"}]}`,
			},
		},
		{
			name: "余额告警_无所属项目且余额类型是点数",
			msg:  balanceAlert("P", nil, "OpenRouter", "点数", 5.0, 10.0, ""),
			want: map[string]string{
				TypeFeishu:   `{"msg_type":"text","content":{"text":"【余额告警】\n\nAPI 调用: P\n服务商: OpenRouter\n当前点数: 5.00\n告警阈值: 10.00\n状态: ⚠️ 点数不足\n来源: credit-monitor"}}`,
				TypeDingTalk: `{"msgtype":"markdown","markdown":{"title":"余额告警","text":"## 余额告警\n\n- **API 调用**: P\n- **服务商**: OpenRouter\n- **当前点数**: 5.00\n- **告警阈值**: 10.00\n- **状态**: ⚠️ 点数不足"}}`,
				TypeWeCom:    `{"msgtype":"text","text":{"content":"【余额告警】\nAPI 调用: P\n服务商: OpenRouter\n当前点数: 5.00\n告警阈值: 10.00\n状态: ⚠️ 点数不足"}}`,
				TypeCustom:   `{"Type":"AlarmNotification","RuleName":"P点数告警","Level":"critical","Resources":[{"ProjectName":"P","OwnerProject":null,"Provider":"OpenRouter","BalanceType":"点数","CurrentValue":5.0,"Threshold":10.0,"Unit":"","Message":"项目 [P] 点数不足，当前: 5.00，阈值: 10.00"}]}`,
			},
		},
		{
			name: "订阅提醒_月付还有三天",
			msg:  SubscriptionAlert("Netflix", &owner, "monthly", 15, 3, 15.99),
			want: map[string]string{
				TypeFeishu:   `{"msg_type":"text","content":{"text":"【订阅续费提醒】\n\n订阅: Netflix\n所属项目: 核心业务\n续费周期: 每月 15 号\n距离续费: 3 天后\n续费金额: 15.99\n来源: credit-monitor"}}`,
				TypeDingTalk: `{"msgtype":"markdown","markdown":{"title":"订阅续费提醒","text":"## 订阅续费提醒\n\n- **订阅**: Netflix\n- **所属项目**: 核心业务\n- **续费周期**: 每月 15 号\n- **距离续费**: 3 天后\n- **续费金额**: 15.99"}}`,
				TypeWeCom:    `{"msgtype":"text","text":{"content":"【订阅续费提醒】\n订阅: Netflix\n所属项目: 核心业务\n续费周期: 每月 15 号\n距离续费: 3 天后\n续费金额: 15.99"}}`,
				TypeCustom:   `{"Type":"SubscriptionReminder","RuleName":"Netflix续费提醒","Level":"warning","Resources":[{"SubscriptionName":"Netflix","OwnerProject":"核心业务","RenewalDay":15,"CycleType":"monthly","DaysUntilRenewal":3,"Amount":15.99,"Message":"订阅 [Netflix] 将在 3 天后（每月 15 号）续费，金额: 15.99"}]}`,
			},
		},
		{
			name: "订阅提醒_年付今天到期",
			msg:  SubscriptionAlert("ChatGPT", nil, "yearly", 315, 0, 20.0),
			want: map[string]string{
				TypeFeishu:   `{"msg_type":"text","content":{"text":"【订阅续费提醒】\n\n订阅: ChatGPT\n续费周期: 每年 3月15日\n距离续费: 今天\n续费金额: 20.0\n来源: credit-monitor"}}`,
				TypeDingTalk: `{"msgtype":"markdown","markdown":{"title":"订阅续费提醒","text":"## 订阅续费提醒\n\n- **订阅**: ChatGPT\n- **续费周期**: 每年 3月15日\n- **距离续费**: 今天\n- **续费金额**: 20.0"}}`,
				TypeWeCom:    `{"msgtype":"text","text":{"content":"【订阅续费提醒】\n订阅: ChatGPT\n续费周期: 每年 3月15日\n距离续费: 今天\n续费金额: 20.0"}}`,
				TypeCustom:   `{"Type":"SubscriptionReminder","RuleName":"ChatGPT续费提醒","Level":"critical","Resources":[{"SubscriptionName":"ChatGPT","OwnerProject":null,"RenewalDay":315,"CycleType":"yearly","DaysUntilRenewal":0,"Amount":20.0,"Message":"订阅 [ChatGPT] 将在 0 天后（每年 3月15日）续费，金额: 20.0"}]}`,
			},
		},
		{
			name: "富文本告警_跑道见底",
			msg:  Custom("余额跑道不足: TestProject", rich, KindRunway),
			want: map[string]string{
				TypeFeishu:   `{"msg_type":"interactive","card":{"header":{"title":{"tag":"plain_text","content":"余额跑道不足: TestProject"},"template":"orange"},"elements":[{"tag":"markdown","content":"**账户**: TestProject\n**所属项目**: 核心业务\n**服务商**: OpenRouter\n**当前余额**: 1,234.50\n**日均消耗**: 120.00（最近 7 天）"}]}}`,
				TypeDingTalk: `{"msgtype":"markdown","markdown":{"title":"余额跑道不足: TestProject","text":"### 余额跑道不足: TestProject\n\n**账户**: TestProject\n**所属项目**: 核心业务\n**服务商**: OpenRouter\n**当前余额**: 1,234.50\n**日均消耗**: 120.00（最近 7 天）"}}`,
				TypeWeCom:    `{"msgtype":"markdown","markdown":{"content":"### 余额跑道不足: TestProject\n\n**账户**: TestProject\n**所属项目**: 核心业务\n**服务商**: OpenRouter\n**当前余额**: 1,234.50\n**日均消耗**: 120.00（最近 7 天）"}}`,
				// 时间戳是本地时间且无时区，取值由 pinnedNow 钉死
				TypeCustom: `{"title":"余额跑道不足: TestProject","content":"**账户**: TestProject\n**所属项目**: 核心业务\n**服务商**: OpenRouter\n**当前余额**: 1,234.50\n**日均消耗**: 120.00（最近 7 天）","source":"credit-monitor","timestamp":"2026-09-16T23:50:26.026504"}`,
			},
		},
	}
}

func TestSendPayloadMatchesPython(t *testing.T) {
	for _, tc := range payloadCases() {
		for _, typ := range SupportedTypes() {
			t.Run(tc.name+"/"+typ, func(t *testing.T) {
				got, _ := sendCaptured(t, typ, tc.msg)
				want := tc.want[typ]

				if typ == TypeCustom && tc.msg.envelope != nil {
					// 信封里有原始数值：Python 写 10000.0、Go 写 10000，是同一个数，
					// 按 token 流比——字段顺序变了照样能查出来。
					assertSameJSON(t, want, got)
					return
				}
				if got != want {
					t.Errorf("报文与 Python 版不一致\n期望: %s\n实际: %s", want, got)
				}
			})
		}
	}
}

// 邮件类告警走富文本那条路，这里只钉飞书卡片，其余平台由上面的用例覆盖。
func TestSendEmailPayload(t *testing.T) {
	service := "OpenAI"
	amount := 20.0
	msg := EmailAlert("财务邮箱", "Your receipt from OpenAI", "billing@openai.com",
		"2026-09-16 10:00:00", []string{"invoice", "续费"}, &service, &amount)

	got, _ := sendCaptured(t, TypeFeishu, msg)
	want := `{"msg_type":"interactive","card":{"header":{"title":{"tag":"plain_text","content":"📧 邮件告警: Your receipt from OpenAI"},"template":"orange"},"elements":[{"tag":"markdown","content":"**邮箱**: 财务邮箱\n**发件人**: billing@openai.com\n**日期**: 2026-09-16 10:00:00\n**服务**: OpenAI\n**金额**: 20.0\n**关键词**: invoice, 续费"}]}}`
	if got != want {
		t.Errorf("邮件告警报文不一致\n期望: %s\n实际: %s", want, got)
	}
}

// 自己拼的 Message 带不出结构化字段，custom 类型要能退回通用报文而不是发个空信封。
func TestSendCustomFallsBackWithoutEnvelope(t *testing.T) {
	msg := Message{Title: "余额告警", Lines: []string{"API 调用: P"}, Kind: KindBalance}

	got, _ := sendCaptured(t, TypeCustom, msg)
	want := `{"title":"余额告警","content":"API 调用: P","source":"credit-monitor","timestamp":"2026-09-16T23:50:26.026504"}`
	if got != want {
		t.Errorf("退化报文不一致\n期望: %s\n实际: %s", want, got)
	}
}

func TestSendSetsJSONContentType(t *testing.T) {
	_, header := sendCaptured(t, TypeFeishu, Custom("标题", []string{"**字段**: 值"}, KindWeeklyReport))
	if got := header.Get("Content-Type"); got != "application/json" {
		t.Errorf("Content-Type = %q，期望 application/json", got)
	}
}

// sendCaptured 起一个假的机器人端点，返回实际发出的报文和请求头。
func sendCaptured(t *testing.T, webhookType string, msg Message) (string, http.Header) {
	t.Helper()

	var body []byte
	var header http.Header
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body, _ = io.ReadAll(r.Body)
		header = r.Header.Clone()
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	n, err := New(srv.URL, webhookType, "credit-monitor", srv.Client())
	if err != nil {
		t.Fatalf("New(%q) 返回错误: %v", webhookType, err)
	}
	n.(*notifier).now = func() time.Time { return pinnedNow }

	if err := n.Send(context.Background(), msg); err != nil {
		t.Fatalf("Send 失败: %v", err)
	}
	return string(body), header
}

// assertSameJSON 按 token 流比较两段 JSON：层级、字段顺序、取值都要一致，
// 只有数字按数值比——Python 的 10000.0 和 Go 的 10000 是同一个数。
func assertSameJSON(t *testing.T, want, got string) {
	t.Helper()

	wantTokens, gotTokens := jsonTokens(t, want), jsonTokens(t, got)
	if len(wantTokens) != len(gotTokens) {
		t.Fatalf("报文结构不一致\n期望: %s\n实际: %s", want, got)
	}
	for i := range wantTokens {
		if !sameToken(wantTokens[i], gotTokens[i]) {
			t.Fatalf("第 %d 个 token 不一致: 期望 %v，实际 %v\n期望报文: %s\n实际报文: %s",
				i, wantTokens[i], gotTokens[i], want, got)
		}
	}
}

func jsonTokens(t *testing.T, raw string) []json.Token {
	t.Helper()

	dec := json.NewDecoder(strings.NewReader(raw))
	dec.UseNumber()
	var out []json.Token
	for {
		tok, err := dec.Token()
		if err == io.EOF {
			return out
		}
		if err != nil {
			t.Fatalf("解析 JSON 失败: %v（%s）", err, raw)
		}
		out = append(out, tok)
	}
}

func sameToken(a, b json.Token) bool {
	an, aok := a.(json.Number)
	bn, bok := b.(json.Number)
	if aok && bok {
		af, aerr := an.Float64()
		bf, berr := bn.Float64()
		return aerr == nil && berr == nil && af == bf
	}
	return a == b
}
