package mailscan

import (
	"context"
	"crypto/tls"
	"fmt"
	"net"
	"strconv"
	"time"

	"github.com/emersion/go-imap/v2"
	"github.com/emersion/go-imap/v2/imapclient"

	"github.com/itswl/balance-alert/internal/model"
)

// defaultPort 是 IMAPS 端口，对应 Python 的 email_config.get('port', 993)：
// 配置里没写（Go 里就是零值）按 993 算。
const defaultPort = 993

// mailConn 是扫描一个邮箱要用到的全部 IMAP 能力。
//
// 抽成接口是为了让扫描流程能脱离真实服务器测试——协议细节全关在本文件里，
// 上面那层只认"给我最近的邮件序号"和"把这批原文拿来"。
type mailConn interface {
	// Search 返回 SINCE since 之后的邮件序号，顺序由服务端给出（由旧到新）。
	Search(since time.Time) ([]uint32, error)
	// Fetch 批量取邮件原文。返回条数可能少于请求数：服务端没给的就是没有。
	Fetch(nums []uint32) ([][]byte, error)
	Close() error
}

// dialFunc 建立一个已登录并选好 INBOX 的连接。Scanner 用它换成假实现来测试。
type dialFunc func(ctx context.Context, m model.Mailbox, timeout time.Duration) (mailConn, error)

type imapConn struct {
	client *imapclient.Client
}

// dialIMAP 连接、登录、选中 INBOX，任何一步失败都把连接关掉再报错。
//
// timeout 只管到"选中 INBOX"为止，之后就撤掉：一个邮箱最多要拉上千封邮件，
// 用一次 HTTP 请求的超时去卡整轮扫描，正常的大邮箱永远扫不完。
func dialIMAP(ctx context.Context, m model.Mailbox, timeout time.Duration) (mailConn, error) {
	addr := net.JoinHostPort(m.Host, strconv.Itoa(mailboxPort(m)))

	conn, err := (&net.Dialer{Timeout: timeout}).DialContext(ctx, "tcp", addr)
	if err != nil {
		return nil, fmt.Errorf("连接 %s 失败: %w", addr, err)
	}
	if timeout > 0 {
		// 端口通了但服务端不搭理的情况下，握手阶段不至于挂死
		_ = conn.SetDeadline(time.Now().Add(timeout))
	}
	if m.UseSSL {
		tlsConn := tls.Client(conn, &tls.Config{ServerName: m.Host, NextProtos: []string{"imap"}})
		if err := tlsConn.HandshakeContext(ctx); err != nil {
			conn.Close()
			return nil, fmt.Errorf("与 %s 的 TLS 握手失败: %w", addr, err)
		}
		conn = tlsConn
	}

	client := imapclient.New(conn, nil)
	if err := client.Login(m.Username, m.Password).Wait(); err != nil {
		client.Close()
		return nil, fmt.Errorf("登录 %s 失败: %w", m.Username, err)
	}
	if _, err := client.Select("INBOX", nil).Wait(); err != nil {
		client.Close()
		return nil, fmt.Errorf("打开 INBOX 失败: %w", err)
	}
	_ = conn.SetDeadline(time.Time{})
	return &imapConn{client: client}, nil
}

func (c *imapConn) Search(since time.Time) ([]uint32, error) {
	// SINCE 只比日期，时间与时区会被服务端忽略
	data, err := c.client.Search(&imap.SearchCriteria{Since: since}, nil).Wait()
	if err != nil {
		return nil, err
	}
	return data.AllSeqNums(), nil
}

func (c *imapConn) Fetch(nums []uint32) ([][]byte, error) {
	if len(nums) == 0 {
		return nil, nil
	}

	// BODY.PEEK[] 取整封原文，内容与 Python 版的 RFC822 一样；
	// 用 PEEK 是为了不把用户的邮件标成已读——监控扫一遍不该动收件箱的状态。
	section := &imap.FetchItemBodySection{Peek: true}
	messages, err := c.client.Fetch(
		imap.SeqSetNum(nums...),
		&imap.FetchOptions{BodySection: []*imap.FetchItemBodySection{section}},
	).Collect()
	if err != nil {
		return nil, err
	}

	raws := make([][]byte, 0, len(messages))
	for _, msg := range messages {
		if raw := msg.FindBodySection(section); len(raw) > 0 {
			raws = append(raws, raw)
		}
	}
	return raws, nil
}

// Close 先 LOGOUT 再断开，服务端才不会把这次连接当成异常掉线（有的邮箱会因此限流）。
func (c *imapConn) Close() error {
	err := c.client.Logout().Wait()
	c.client.Close()
	return err
}

func mailboxPort(m model.Mailbox) int {
	if m.Port <= 0 {
		return defaultPort
	}
	return m.Port
}
