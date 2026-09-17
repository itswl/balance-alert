package mailscan

import (
	"bytes"
	"crypto/md5"
	"encoding/hex"
	"fmt"
	"io"
	"regexp"
	"strings"

	"github.com/emersion/go-message"
	// 注册 GBK / Big5 / ISO-8859 等字符集：国内账单邮件大量用 GBK，
	// 不注册的话主题和正文会变成乱码，关键词自然一个也匹配不上。
	_ "github.com/emersion/go-message/charset"
)

// maxPartDepth 限制嵌套层数：正常邮件两三层就到头了，这道闸门防的是构造出来的深层嵌套。
const maxPartDepth = 10

// htmlTag 匹配 HTML 标签，替换成空格而不是直接删掉——标签常常是词与词之间唯一的分隔。
var htmlTag = regexp.MustCompile(`<[^>]+>`)

// parsedMessage 是一封邮件里扫描要用到的几样东西。
type parsedMessage struct {
	ID      string // 本次扫描内的去重键
	Subject string
	Sender  string
	Date    string
	Body    string
}

// parseMessage 解析一封 RFC822 原文。返回的 parsedMessage 一定可用，
// error 只是说明这封邮件的格式有问题，值得记一条日志。
//
// 字符集或传输编码不认识时 message.Read 仍然给得出可读的 Entity，这里照样接着用：
// 认不出的字节变成替换符，总好过整封邮件被丢掉——关键词多半还在能解出来的那部分里。
func parseMessage(raw []byte) (parsedMessage, error) {
	ent, err := message.Read(bytes.NewReader(raw))
	if ent == nil {
		// 邮件头坏到解析不出来时，把整封原文当正文接着扫——关键词照样能命中。
		// 去重键退回原文摘要，否则所有坏邮件会挤成同一个 ID 互相顶掉。
		sum := md5.Sum(raw)
		return parsedMessage{ID: hex.EncodeToString(sum[:]), Body: string(raw)}, fmt.Errorf("解析邮件失败: %w", err)
	}
	return parsedMessage{
		ID:      messageID(&ent.Header),
		Subject: headerText(&ent.Header, "Subject"),
		Sender:  headerText(&ent.Header, "From"),
		Date:    headerText(&ent.Header, "Date"),
		Body:    extractText(ent),
	}, nil
}

// headerText 解 MIME 编码头（=?utf-8?B?...?=），解不动就退回原样——
// 半通不通的头总比空字符串强，起码还能在日志里看出这封信是谁发的。
func headerText(h *message.Header, key string) string {
	value, err := h.Text(key)
	if err != nil {
		return h.Get(key)
	}
	return value
}

// messageID 优先用 Message-ID，没有的邮件退回 md5(date|subject|from)。
// 取的都是没解码的原始头：解码结果会随实现变，原始字节不会，去重键必须稳定。
func messageID(h *message.Header) string {
	if id := strings.TrimSpace(h.Get("Message-ID")); id != "" {
		return id
	}
	sum := md5.Sum([]byte(h.Get("Date") + "|" + h.Get("Subject") + "|" + h.Get("From")))
	return hex.EncodeToString(sum[:])
}

// extractText 取出正文文本：text/plain 直接用，text/html 去掉标签，附件跳过。
func extractText(ent *message.Entity) string {
	var texts []string
	collectText(ent, &texts, 0)
	return strings.Join(texts, "\n")
}

func collectText(ent *message.Entity, texts *[]string, depth int) {
	// 容器本身没有正文，但要往里走：附件判断留给叶子节点做，
	// 否则被整体标成 attachment 的转发邮件里，正文就一起丢了
	if mr := ent.MultipartReader(); mr != nil {
		if depth >= maxPartDepth {
			return
		}
		for {
			part, err := mr.NextPart()
			if err != nil {
				return // io.EOF，或者这封邮件的分段坏了——后面也读不出东西
			}
			collectText(part, texts, depth+1)
		}
	}

	if disp, _, _ := ent.Header.ContentDisposition(); strings.EqualFold(disp, "attachment") {
		return
	}
	contentType, _, _ := ent.Header.ContentType()
	if contentType != "text/plain" && contentType != "text/html" {
		return
	}

	// 读坏了也把已经读到的部分留下，半截正文里的关键词照样算数
	body, _ := io.ReadAll(ent.Body)
	text := string(body)
	if contentType == "text/html" {
		text = htmlTag.ReplaceAllString(text, " ")
	}
	if text != "" {
		*texts = append(*texts, text)
	}
}
