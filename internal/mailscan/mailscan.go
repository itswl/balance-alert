// Package mailscan 扫 IMAP 邮箱，把"欠费 / 续费 / 停机"这类提醒邮件变成告警。
//
// 很多账单只发到邮箱，等人翻到的时候服务已经停了——所以要有人替值班同学看邮件。
// 邮箱之间并发扫描，一个连不上不影响其它邮箱：它自己记一条错误，再单独发一条系统告警。
//
// 去重分两层：一次扫描内同一封邮件（Message-ID）只处理一次，多个邮箱共享这个集合，
// 因为同一封通知常常抄送到好几个被扫的邮箱；跨扫描则问 store 最近几天有没有通知过同一封。
package mailscan

import (
	"context"
	"log/slog"
	"strings"
	"sync"
	"time"

	"github.com/itswl/balance-alert/internal/model"
	"github.com/itswl/balance-alert/internal/notify"
	"github.com/itswl/balance-alert/internal/store"
)

// 与 Python 版一致的几个上限。
const (
	maxMailboxWorkers = 5    // 同时扫描的邮箱数
	batchSize         = 100  // 一次 IMAP FETCH 拉多少封
	defaultMaxEmails  = 1000 // MaxEmails 没给时的上限，对应 MAX_EMAILS_TO_SCAN 的默认值

	// 连接重试节奏照搬 Python 的 tenacity(stop_after_attempt(3), wait_exponential(1, 4, 10))：
	// 一共三次，两次重试各等 4 秒。网络抖动和邮箱限流很常见，重来一次多半就过去了。
	connectAttempts   = 3
	connectRetryDelay = 4 * time.Second
)

// Scanner 扫一批邮箱。零值不可用：至少要有 Store（没数据库就传 store.Null()）。
type Scanner struct {
	Store     store.Store
	Notifier  notify.Notifier
	Log       *slog.Logger
	Keywords  []string      // 为空时用 DefaultAlertKeywords
	MaxEmails int           // 单个邮箱最多扫多少封，零值表示没配置，用 defaultMaxEmails
	Timeout   time.Duration // 连接与登录的超时，不限制整轮扫描

	// OnNotify 每发一次通知回调一次，用于记指标。可空。
	OnNotify func(kind string, ok bool)

	// 下面两个只给测试换实现，生产走默认值。
	dial      dialFunc
	retryWait time.Duration
}

// scanState 是一次扫描里各邮箱共享的东西。
type scanState struct {
	matcher *matcher
	seen    seenSet
	days    int
	dryRun  bool
}

// Scan 扫描给定的邮箱，返回逐邮箱统计与命中的告警邮件。
//
// 单个邮箱失败只影响它自己那条 MailboxResult；dryRun 时一切照跑，
// 既不查去重也不发通知——页面上的"试扫一下"就是靠它。
func (s *Scanner) Scan(ctx context.Context, mailboxes []model.Mailbox, days int, dryRun bool) model.ScanResult {
	result := model.ScanResult{
		Days:      days,
		DryRun:    dryRun,
		Mailboxes: []model.MailboxResult{},
		Alerts:    []model.EmailAlert{},
	}
	if len(mailboxes) == 0 {
		s.log().Error("未配置邮箱信息或所有邮箱均已禁用")
		return result
	}

	s.log().Info("开始扫描邮箱", "mailboxes", len(mailboxes), "days", days, "dry_run", dryRun)
	state := &scanState{matcher: newMatcher(s.keywords()), days: days, dryRun: dryRun}

	// 结果按输入顺序回填，页面上的邮箱顺序才不会每次扫描都变
	results := make([]model.MailboxResult, len(mailboxes))
	alerts := make([][]model.EmailAlert, len(mailboxes))
	workers := min(len(mailboxes), maxMailboxWorkers)

	jobs := make(chan int)
	var wg sync.WaitGroup
	for range workers {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for i := range jobs {
				results[i], alerts[i] = s.scanMailbox(ctx, mailboxes[i], state)
			}
		}()
	}
	for i := range mailboxes {
		jobs <- i
	}
	close(jobs)
	wg.Wait()

	result.Mailboxes = results
	for _, list := range alerts {
		result.Alerts = append(result.Alerts, list...)
	}
	s.logSummary(result)
	return result
}

// scanMailbox 扫一个邮箱。任何失败都记进 MailboxResult.Error，不向外抛，
// 已经扫到的邮件与告警照样留下——半截结果也比丢掉强。
func (s *Scanner) scanMailbox(ctx context.Context, m model.Mailbox, state *scanState) (model.MailboxResult, []model.EmailAlert) {
	name := displayName(m)
	out := model.MailboxResult{
		Name:     name,
		Host:     m.Host,
		Port:     mailboxPort(m),
		Username: m.Username,
		Success:  true,
	}
	if m.Host == "" || m.Username == "" || m.Password == "" {
		s.log().Warn("邮箱配置不完整，跳过", "mailbox", name)
		out.Success = false
		out.Error = model.Ptr("配置不完整，需要 host / username / password")
		return out, nil
	}

	total, alerts, err := s.scanInbox(ctx, m, name, state)
	out.TotalEmails = total
	out.AlertCount = len(alerts)
	if err != nil {
		out.Success = false
		out.Error = model.Ptr(err.Error())
		s.log().Error("扫描邮箱失败", "mailbox", name, "error", err)
		if !state.dryRun {
			s.sendMailboxError(ctx, name, m.Host, err.Error())
		}
	}
	return out, alerts
}

// scanInbox 连上邮箱，逐批检查最近 days 天的邮件。
// 出错时已经扫到的数量与告警一并返回，调用方据此保留半截结果。
func (s *Scanner) scanInbox(ctx context.Context, m model.Mailbox, name string, state *scanState) (int, []model.EmailAlert, error) {
	conn, err := s.connect(ctx, m)
	if err != nil {
		return 0, nil, err
	}
	defer func() {
		if err := conn.Close(); err != nil {
			s.log().Warn("断开邮箱连接时出错", "mailbox", name, "error", err)
		}
	}()

	// 与 Python 的 datetime.now() - timedelta(days=days) 一致：按本地时区的日期过滤
	since := time.Now().Add(-time.Duration(state.days) * 24 * time.Hour)
	nums, err := conn.Search(since)
	if err != nil {
		return 0, nil, err
	}
	if len(nums) == 0 {
		s.log().Info("没有需要检查的邮件", "mailbox", name)
		return 0, nil, nil
	}

	if limit := s.maxEmails(); len(nums) > limit {
		s.log().Warn("邮件数量超过上限，只扫最新的", "mailbox", name, "found", len(nums), "limit", limit)
		nums = nums[len(nums)-limit:]
	}
	total := len(nums)
	s.log().Info("找到邮件", "mailbox", name, "count", total)

	var alerts []model.EmailAlert
	for start := 0; start < total; start += batchSize {
		// 页面上把请求取消了就别接着拉，剩下的邮件下一轮再看
		if err := ctx.Err(); err != nil {
			return total, alerts, err
		}
		end := min(start+batchSize, total)
		for _, raw := range s.fetchBatch(conn, nums[start:end], name) {
			if alert, ok := s.inspect(ctx, raw, name, state); ok {
				alerts = append(alerts, alert)
			}
		}
		s.log().Info("扫描进度", "mailbox", name, "scanned", end, "total", total)
	}

	s.log().Info("邮箱扫描汇总", "mailbox", name, "total_emails", total, "alert_count", len(alerts))
	return total, alerts, nil
}

// fetchBatch 批量取一批邮件，整批失败时降级为逐封取——
// 一封邮件格式坏掉就让整批拿不到，剩下 99 封没道理跟着陪葬。
func (s *Scanner) fetchBatch(conn mailConn, nums []uint32, name string) [][]byte {
	raws, err := conn.Fetch(nums)
	if err == nil {
		return raws
	}
	s.log().Warn("批量获取邮件失败，降级为逐封获取", "mailbox", name, "error", err)

	raws = make([][]byte, 0, len(nums))
	for _, num := range nums {
		one, err := conn.Fetch([]uint32{num})
		if err != nil {
			s.log().Warn("获取邮件失败", "mailbox", name, "seq", num, "error", err)
			continue
		}
		raws = append(raws, one...)
	}
	return raws
}

// inspect 判断一封邮件是不是告警邮件；是则（按需）发通知并返回明细。
func (s *Scanner) inspect(ctx context.Context, raw []byte, mailbox string, state *scanState) (model.EmailAlert, bool) {
	msg, err := parseMessage(raw)
	if err != nil {
		// 解析失败的邮件不丢，按原文接着扫，只是记一笔
		s.log().Warn("邮件格式有问题，按原文扫描", "mailbox", mailbox, "error", err)
	}
	if !state.seen.mark(msg.ID) {
		return model.EmailAlert{}, false
	}

	keywords := state.matcher.match(msg.Subject, msg.Body)
	if len(keywords) == 0 {
		return model.EmailAlert{}, false
	}

	service, amount := extractServiceInfo(msg.Subject, msg.Body)
	alert := model.EmailAlert{
		Mailbox:     mailbox,
		Subject:     msg.Subject,
		Sender:      msg.Sender,
		Date:        msg.Date,
		Keywords:    keywords,
		ServiceName: &service,
		Amount:      amount,
	}

	attrs := []any{
		"mailbox", mailbox, "sender", msg.Sender, "subject", msg.Subject,
		"date", msg.Date, "keywords", strings.Join(keywords, ", "), "service", service,
	}
	if amount != nil {
		attrs = append(attrs, "amount", *amount)
	}
	s.log().Warn("发现告警邮件", attrs...)

	switch {
	case state.dryRun:
		s.log().Info("测试模式，跳过发送告警", "mailbox", mailbox, "subject", msg.Subject)
	case s.duplicated(ctx, alert, state.days):
		s.log().Info("邮件告警已发送过，跳过重复通知", "mailbox", mailbox, "subject", msg.Subject)
	default:
		alert.AlertSent = s.send(ctx, alert)
	}
	return alert, true
}

// duplicated 问数据库这封邮件最近有没有通知过。查不动就按"没通知过"走：
// 宁可多发一条，也不能因为数据库抽风把欠费提醒吞掉。
func (s *Scanner) duplicated(ctx context.Context, alert model.EmailAlert, days int) bool {
	recent, err := s.Store.HasRecentEmailAlert(ctx, alert.Mailbox, alert.Sender, alert.Subject, alert.Date, max(days, 1))
	if err != nil {
		s.log().Warn("查询邮件告警去重失败，按未通知过处理", "mailbox", alert.Mailbox, "error", err)
		return false
	}
	return recent
}

// send 发一封邮件告警并留痕。留痕带上发送结果，与 Python 版一致：
// 没发出去的也要记，下次才知道这封邮件已经处理过、现在是什么状态。
func (s *Scanner) send(ctx context.Context, alert model.EmailAlert) bool {
	if s.Notifier == nil {
		s.log().Error("未配置 webhook 地址")
		return false
	}

	msg := notify.EmailAlert(alert.Mailbox, alert.Subject, alert.Sender, alert.Date,
		alert.Keywords, alert.ServiceName, alert.Amount)
	err := s.Notifier.Send(ctx, msg)
	if s.OnNotify != nil {
		s.OnNotify(msg.Kind, err == nil)
	}
	if err != nil {
		s.log().Error("发送邮件告警失败", "mailbox", alert.Mailbox, "subject", alert.Subject, "error", err)
	}

	sent := err == nil
	if err := s.Store.SaveEmailAlert(ctx, store.EmailAlertRecord{
		Mailbox: alert.Mailbox, Sender: alert.Sender, Subject: alert.Subject, Date: alert.Date,
		ServiceName: alert.ServiceName, Amount: alert.Amount,
		Keywords: alert.Keywords, AlertSent: sent,
	}); err != nil {
		s.log().Warn("记录邮件告警失败", "mailbox", alert.Mailbox, "error", err)
	}
	return sent
}

// sendMailboxError 邮箱连不上时发一条系统告警——没人看邮件这件事本身就是故障。
func (s *Scanner) sendMailboxError(ctx context.Context, mailbox, host, reason string) {
	if s.Notifier == nil {
		return
	}
	msg := notify.MailboxError(mailbox, host, reason)
	err := s.Notifier.Send(ctx, msg)
	if s.OnNotify != nil {
		s.OnNotify(msg.Kind, err == nil)
	}
	if err != nil {
		s.log().Error("发送邮箱故障告警失败", "mailbox", mailbox, "error", err)
	}
}

// connect 建连接，失败按 Python 的节奏重试。
func (s *Scanner) connect(ctx context.Context, m model.Mailbox) (mailConn, error) {
	dial := s.dial
	if dial == nil {
		dial = dialIMAP
	}
	wait := s.retryWait
	if wait <= 0 {
		wait = connectRetryDelay
	}

	for attempt := 1; ; attempt++ {
		conn, err := dial(ctx, m, s.Timeout)
		if err == nil {
			s.log().Info("成功连接邮箱", "mailbox", displayName(m), "host", m.Host)
			return conn, nil
		}
		if attempt >= connectAttempts {
			return nil, err
		}
		s.log().Warn("连接邮箱失败，稍后重试", "mailbox", displayName(m), "attempt", attempt, "error", err)
		if waitErr := sleep(ctx, wait); waitErr != nil {
			return nil, err
		}
	}
}

// seenSet 记住本次扫描已经处理过的邮件。多个邮箱并发写，必须加锁。
type seenSet struct {
	mu  sync.Mutex
	ids map[string]struct{}
}

// mark 第一次见到这封邮件返回 true，之后都是 false。
func (s *seenSet) mark(id string) bool {
	s.mu.Lock()
	defer s.mu.Unlock()
	if _, ok := s.ids[id]; ok {
		return false
	}
	if s.ids == nil {
		s.ids = make(map[string]struct{})
	}
	s.ids[id] = struct{}{}
	return true
}

// keywords 为空时用默认词表，与 Python 版 _load_keywords 的兜底一致。
func (s *Scanner) keywords() []string {
	if len(s.Keywords) > 0 {
		return s.Keywords
	}
	return DefaultAlertKeywords
}

// maxEmails 没配置时用默认上限；配成负数按 1 算，与 Python 的 max(1, ...) 同义。
func (s *Scanner) maxEmails() int {
	if s.MaxEmails == 0 {
		return defaultMaxEmails
	}
	return max(s.MaxEmails, 1)
}

func (s *Scanner) logSummary(result model.ScanResult) {
	total, sent := 0, 0
	for _, m := range result.Mailboxes {
		total += m.TotalEmails
	}
	for _, a := range result.Alerts {
		if a.AlertSent {
			sent++
		}
	}
	s.log().Info("邮箱扫描总汇总",
		"mailboxes", len(result.Mailboxes), "total_emails", total,
		"total_alerts", len(result.Alerts), "alerts_sent", sent)
}

func (s *Scanner) log() *slog.Logger {
	if s.Log != nil {
		return s.Log
	}
	return slog.Default()
}

// displayName 与 Python 的 _mailbox_display_name 一致：没名字就用账号。
func displayName(m model.Mailbox) string {
	if m.Name != "" {
		return m.Name
	}
	if m.Username != "" {
		return m.Username
	}
	return "(未命名)"
}

// sleep 等一段时间，ctx 取消就立刻回来，别让整轮扫描卡在重试上。
func sleep(ctx context.Context, d time.Duration) error {
	timer := time.NewTimer(d)
	defer timer.Stop()
	select {
	case <-timer.C:
		return nil
	case <-ctx.Done():
		return ctx.Err()
	}
}
