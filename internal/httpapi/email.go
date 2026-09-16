package httpapi

import (
	"net/http"
	"time"

	"github.com/itswl/balance-alert/internal/model"
)

// maxScanDays 立即扫描最多回看多少天。再多就该去翻邮箱本身了。
const maxScanDays = 30

// maskedMailbox 是邮箱配置的对外形状，密码只表示"有没有设过"。
type maskedMailbox struct {
	Name     string `json:"name"`
	Host     string `json:"host"`
	Port     int    `json:"port"`
	Username string `json:"username"`
	Password string `json:"password"`
	UseSSL   bool   `json:"use_ssl"`
	Enabled  bool   `json:"enabled"`
	FromEnv  bool   `json:"from_env"`
}

func (s *Server) handleListMailboxes(w http.ResponseWriter, r *http.Request) {
	cfg := s.Resolver.Load(r.Context())
	mailboxes := make([]maskedMailbox, 0, len(cfg.Mailboxes))
	for _, m := range cfg.Mailboxes {
		password := ""
		if m.Password != "" {
			password = "***"
		}
		mailboxes = append(mailboxes, maskedMailbox{
			Name: m.Name, Host: m.Host, Port: m.Port, Username: m.Username,
			Password: password, UseSSL: m.UseSSL, Enabled: m.Enabled, FromEnv: m.FromEnv,
		})
	}
	etagJSON(w, r, map[string]any{"status": "success", "emails": mailboxes})
}

type mailboxRequest struct {
	Name     string  `json:"name"`
	Host     *string `json:"host"`
	Port     *int    `json:"port"`
	Username *string `json:"username"`
	Password *string `json:"password"`
	UseSSL   *bool   `json:"use_ssl"`
	Enabled  *bool   `json:"enabled"`
}

// handleSaveMailbox 新增或更新邮箱。更新时密码留空表示不变，
// 页面展示的是星号，原样提交不能把真密码盖掉。
func (s *Server) handleSaveMailbox(w http.ResponseWriter, r *http.Request) {
	if !s.requireDynamicConfig(w, "邮箱配置") {
		return
	}
	var body mailboxRequest
	if !decodeJSON(w, r, &body) {
		return
	}
	body.Name = trimSpace(body.Name)
	if body.Name == "" {
		failValidation(w, []string{"name: 不能为空"})
		return
	}

	cfg := s.Resolver.Load(r.Context())
	existing := findMailbox(cfg.Mailboxes, body.Name)
	isNew := existing == nil

	target := model.Mailbox{Name: body.Name, Port: 993, UseSSL: true, Enabled: true}
	if existing != nil {
		target = *existing
	}
	if body.Host != nil && *body.Host != "" {
		target.Host = trimSpace(*body.Host)
	}
	if body.Username != nil && *body.Username != "" {
		target.Username = trimSpace(*body.Username)
	}
	// 星号是展示用的占位，不能当成真密码写回去
	if body.Password != nil && trimSpace(*body.Password) != "" && trimSpace(*body.Password) != "***" {
		target.Password = *body.Password
	}
	if body.Port != nil && *body.Port > 0 {
		target.Port = *body.Port
	}
	if body.UseSSL != nil {
		target.UseSSL = *body.UseSSL
	}
	if body.Enabled != nil {
		target.Enabled = *body.Enabled
	}

	if isNew {
		var missing []string
		if target.Host == "" {
			missing = append(missing, "host")
		}
		if target.Username == "" {
			missing = append(missing, "username")
		}
		if target.Password == "" {
			missing = append(missing, "password")
		}
		if len(missing) > 0 {
			fail(w, http.StatusBadRequest, "新增邮箱缺少必要参数: "+joinComma(missing))
			return
		}
	}
	target.FromEnv = false

	if err := s.Store.UpsertMailbox(r.Context(), target); err != nil {
		s.log().Error("保存邮箱配置失败", "mailbox", body.Name, "error", err)
		fail(w, storeWriteStatus(err), "保存失败")
		return
	}
	s.log().Info("[AUDIT] 保存邮箱", "mailbox", body.Name, "new", isNew)

	action := "更新"
	if isNew {
		action = "添加"
	}
	ok(w, map[string]any{"message": "邮箱 [" + body.Name + "] 已" + action})
}

func (s *Server) handleDeleteMailbox(w http.ResponseWriter, r *http.Request) {
	if !s.requireDynamicConfig(w, "邮箱配置") {
		return
	}
	var body nameRequest
	if !decodeJSON(w, r, &body) {
		return
	}
	if body.Name == "" {
		fail(w, http.StatusBadRequest, "缺少必要参数: name")
		return
	}
	cfg := s.Resolver.Load(r.Context())
	existing := findMailbox(cfg.Mailboxes, body.Name)
	if existing == nil {
		fail(w, http.StatusNotFound, "未找到邮箱: "+body.Name)
		return
	}
	if existing.FromEnv {
		fail(w, http.StatusBadRequest, "邮箱 ["+body.Name+"] 来自环境变量自动发现，请移除对应的 EMAIL_* 变量后重启")
		return
	}
	if err := s.Store.DeleteMailbox(r.Context(), body.Name); err != nil {
		fail(w, storeWriteStatus(err), "删除失败")
		return
	}
	s.log().Info("[AUDIT] 删除邮箱", "mailbox", body.Name)
	ok(w, map[string]any{"message": "邮箱 [" + body.Name + "] 已删除"})
}

func (s *Server) handleEmailScanState(w http.ResponseWriter, r *http.Request) {
	etagJSON(w, r, s.State.EmailScan())
}

type scanRequest struct {
	Days *int `json:"days"`
}

// handleEmailScan 立即扫描所有启用的邮箱，结果写进看板状态。
func (s *Server) handleEmailScan(w http.ResponseWriter, r *http.Request) {
	days := 1
	if r.ContentLength > 0 {
		var body scanRequest
		if !decodeJSON(w, r, &body) {
			return
		}
		if body.Days != nil {
			days = *body.Days
		}
	}
	if days < 1 || days > maxScanDays {
		fail(w, http.StatusBadRequest, "days 必须是 1-"+itoa(maxScanDays)+" 之间的整数")
		return
	}

	if busy := s.scanGuard.acquire(); busy != "" {
		fail(w, http.StatusTooManyRequests, "扫描"+busy)
		return
	}
	defer s.scanGuard.release()

	cfg := s.Resolver.Load(r.Context())
	mailboxes := cfg.EnabledMailboxes()
	if len(mailboxes) == 0 {
		fail(w, http.StatusBadRequest, "未配置邮箱或所有邮箱均已停用")
		return
	}

	dryRun := !s.Settings.EnableWebAlarm
	started := time.Now()
	result := s.Scanner.Scan(r.Context(), mailboxes, days, dryRun)
	s.State.SetEmailScan(result)
	if s.OnEmailScanned != nil {
		s.OnEmailScanned(result)
	}

	summary := s.State.EmailScan().Summary
	s.log().Info("[AUDIT] 邮箱扫描", "days", days, "dry_run", dryRun,
		"mailboxes", len(result.Mailboxes), "alerts", len(result.Alerts))
	ok(w, map[string]any{
		"message": "扫描完成：" + itoa(summary.TotalEmails) + " 封邮件，" +
			itoa(summary.TotalAlerts) + " 封告警",
		"summary":                summary,
		"mailboxes":              result.Mailboxes,
		"dry_run":                dryRun,
		"execution_time_seconds": round2(time.Since(started).Seconds()),
	})
}

func findMailbox(mailboxes []model.Mailbox, name string) *model.Mailbox {
	for i := range mailboxes {
		if mailboxes[i].Name == name {
			return &mailboxes[i]
		}
	}
	return nil
}

func joinComma(items []string) string {
	out := ""
	for i, item := range items {
		if i > 0 {
			out += ", "
		}
		out += item
	}
	return out
}

func itoa(n int) string {
	if n == 0 {
		return "0"
	}
	negative := n < 0
	if negative {
		n = -n
	}
	var digits []byte
	for n > 0 {
		digits = append([]byte{byte('0' + n%10)}, digits...)
		n /= 10
	}
	if negative {
		return "-" + string(digits)
	}
	return string(digits)
}
