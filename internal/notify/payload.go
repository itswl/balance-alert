package notify

import "strings"

// 各平台的报文结构。结构体字段顺序就是 JSON 里的字段顺序，是按各平台文档排的，
// 别为了好看重排——飞书卡片按 header/elements 的顺序渲染，自定义那头有系统在按字段名取值。

type feishuTextPayload struct {
	MsgType string            `json:"msg_type"`
	Content feishuTextContent `json:"content"`
}

type feishuTextContent struct {
	Text string `json:"text"`
}

type feishuCardPayload struct {
	MsgType string     `json:"msg_type"`
	Card    feishuCard `json:"card"`
}

type feishuCard struct {
	Header   feishuCardHeader    `json:"header"`
	Elements []feishuCardElement `json:"elements"`
}

type feishuCardHeader struct {
	Title    feishuCardTitle `json:"title"`
	Template string          `json:"template"`
}

type feishuCardTitle struct {
	Tag     string `json:"tag"`
	Content string `json:"content"`
}

type feishuCardElement struct {
	Tag     string `json:"tag"`
	Content string `json:"content"`
}

type dingtalkPayload struct {
	MsgType  string           `json:"msgtype"`
	Markdown dingtalkMarkdown `json:"markdown"`
}

type dingtalkMarkdown struct {
	Title string `json:"title"`
	Text  string `json:"text"`
}

type wecomTextPayload struct {
	MsgType string           `json:"msgtype"`
	Text    wecomTextContent `json:"text"`
}

type wecomTextContent struct {
	Content string `json:"content"`
}

type wecomMarkdownPayload struct {
	MsgType  string        `json:"msgtype"`
	Markdown wecomMarkdown `json:"markdown"`
}

type wecomMarkdown struct {
	Content string `json:"content"`
}

// customPayload 是自定义 webhook 的通用报文，接收端自己去解析正文。
type customPayload struct {
	Title     string `json:"title"`
	Content   string `json:"content"`
	Source    string `json:"source"`
	Timestamp string `json:"timestamp"`
}

// envelope 是自定义 webhook 的结构化信封：余额和订阅的字段是有语义的，
// 对面的告警系统按 Type/Level 分流、从 Resources 里取原始数值，所以不能只发一段文本。
// 首字母大写的字段名是对面定的，改了它就取不到值。
type envelope struct {
	Type      string `json:"Type"`
	RuleName  string `json:"RuleName"`
	Level     string `json:"Level"`
	Resources []any  `json:"Resources"`
}

type balanceResource struct {
	ProjectName  string  `json:"ProjectName"`
	OwnerProject *string `json:"OwnerProject"`
	Provider     string  `json:"Provider"`
	BalanceType  string  `json:"BalanceType"`
	CurrentValue float64 `json:"CurrentValue"`
	Threshold    float64 `json:"Threshold"`
	Unit         string  `json:"Unit"`
	Message      string  `json:"Message"`
}

type subscriptionResource struct {
	SubscriptionName string  `json:"SubscriptionName"`
	OwnerProject     *string `json:"OwnerProject"`
	RenewalDay       int     `json:"RenewalDay"`
	CycleType        string  `json:"CycleType"`
	DaysUntilRenewal int     `json:"DaysUntilRenewal"`
	Amount           float64 `json:"Amount"`
	Message          string  `json:"Message"`
}

// payload 按平台和告警类别挑报文。
//
// 余额、订阅是"字段少、要能被系统消费"的告警，发纯文本（或结构化信封）；
// 跑道、邮件、周报的正文本身就是 Markdown，走富文本卡片。Kind 正好把这两拨分开。
func (n *notifier) payload(msg Message) any {
	text := strings.Join(msg.Lines, "\n")
	if msg.Kind == KindBalance || msg.Kind == KindSubscription {
		return n.plainPayload(msg.Title, text, msg.envelope)
	}
	return n.richPayload(msg.Title, text)
}

func (n *notifier) plainPayload(title, text string, env *envelope) any {
	switch n.typ {
	case TypeFeishu:
		return feishuTextPayload{
			MsgType: "text",
			Content: feishuTextContent{Text: "【" + title + "】\n\n" + text + "\n来源: " + n.source},
		}
	case TypeDingTalk:
		return dingtalkPayload{
			MsgType:  "markdown",
			Markdown: dingtalkMarkdown{Title: title, Text: "## " + title + "\n\n" + dingtalkList(text)},
		}
	case TypeCustom:
		if env != nil {
			return env
		}
		// 外部自己拼的 Message 带不出结构化字段，只能退回通用报文
		return n.customPayload(title, text)
	default: // wecom
		return wecomTextPayload{
			MsgType: "text",
			Text:    wecomTextContent{Content: "【" + title + "】\n" + text},
		}
	}
}

func (n *notifier) richPayload(title, content string) any {
	switch n.typ {
	case TypeFeishu:
		return feishuCardPayload{
			MsgType: "interactive",
			Card: feishuCard{
				Header: feishuCardHeader{
					Title:    feishuCardTitle{Tag: "plain_text", Content: title},
					Template: "orange",
				},
				Elements: []feishuCardElement{{Tag: "markdown", Content: content}},
			},
		}
	case TypeDingTalk:
		return dingtalkPayload{
			MsgType:  "markdown",
			Markdown: dingtalkMarkdown{Title: title, Text: "### " + title + "\n\n" + content},
		}
	case TypeWeCom:
		return wecomMarkdownPayload{
			MsgType:  "markdown",
			Markdown: wecomMarkdown{Content: "### " + title + "\n\n" + content},
		}
	default: // custom
		return n.customPayload(title, content)
	}
}

func (n *notifier) customPayload(title, content string) customPayload {
	return customPayload{Title: title, Content: content, Source: n.source, Timestamp: isoLocal(n.now())}
}

// dingtalkList 把 "键: 值" 的裸文本转成 Markdown 列表并给键加粗：
// 钉钉的 markdown 消息不认换行，不转成列表就会糊成一行。
func dingtalkList(text string) string {
	lines := strings.Split(text, "\n")
	out := make([]string, 0, len(lines))
	for _, line := range lines {
		if key, value, found := strings.Cut(line, ": "); found {
			out = append(out, "- **"+key+"**: "+value)
			continue
		}
		out = append(out, "- "+line)
	}
	return strings.Join(out, "\n")
}
