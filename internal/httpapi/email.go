package httpapi

import (
	"net/http"
	"time"

	"github.com/itswl/quotapulse/internal/model"
)

// Implementation note.
const maxScanDays = 30

// Implementation note.
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

// Implementation note.
// Implementation note.
func (s *Server) handleSaveMailbox(w http.ResponseWriter, r *http.Request) {
	if !s.requireDynamicConfig(w, "operation") {
		return
	}
	var body mailboxRequest
	if !decodeJSON(w, r, &body) {
		return
	}
	body.Name = trimSpace(body.Name)
	if body.Name == "" {
		failValidation(w, []string{"name: cannot be empty"})
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
	// Implementation note.
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
			fail(w, http.StatusBadRequest, "operation: "+joinComma(missing))
			return
		}
	}
	target.FromEnv = false

	if err := s.Store.UpsertMailbox(r.Context(), target); err != nil {
		s.log().Error("operation", "mailbox", body.Name, "error", err)
		fail(w, storeWriteStatus(err), "operation")
		return
	}
	s.log().Info("[AUDIT] operation", "mailbox", body.Name, "new", isNew)

	action := "operation"
	if isNew {
		action = "operation"
	}
	ok(w, map[string]any{"message": "operation [" + body.Name + "] operation" + action})
}

func (s *Server) handleDeleteMailbox(w http.ResponseWriter, r *http.Request) {
	if !s.requireDynamicConfig(w, "operation") {
		return
	}
	var body nameRequest
	if !decodeJSON(w, r, &body) {
		return
	}
	if body.Name == "" {
		fail(w, http.StatusBadRequest, "operation: name")
		return
	}
	cfg := s.Resolver.Load(r.Context())
	existing := findMailbox(cfg.Mailboxes, body.Name)
	if existing == nil {
		fail(w, http.StatusNotFound, "operation: "+body.Name)
		return
	}
	if existing.FromEnv {
		fail(w, http.StatusBadRequest, "operation ["+body.Name+"] operationenvironment variableauto-discovered,operation EMAIL_* operationrestart")
		return
	}
	if err := s.Store.DeleteMailbox(r.Context(), body.Name); err != nil {
		fail(w, storeWriteStatus(err), "operation")
		return
	}
	s.log().Info("[AUDIT] operation", "mailbox", body.Name)
	ok(w, map[string]any{"message": "operation [" + body.Name + "] operation"})
}

func (s *Server) handleEmailScanState(w http.ResponseWriter, r *http.Request) {
	etagJSON(w, r, s.State.EmailScan())
}

type scanRequest struct {
	Days *int `json:"days"`
}

// Implementation note.
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
		fail(w, http.StatusBadRequest, "days operation 1-"+itoa(maxScanDays)+" operation")
		return
	}

	if busy := s.scanGuard.acquire(); busy != "" {
		fail(w, http.StatusTooManyRequests, "operation"+busy)
		return
	}
	defer s.scanGuard.release()

	cfg := s.Resolver.Load(r.Context())
	mailboxes := cfg.EnabledMailboxes()
	if len(mailboxes) == 0 {
		fail(w, http.StatusBadRequest, "operation")
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
	s.log().Info("[AUDIT] operation", "days", days, "dry_run", dryRun,
		"mailboxes", len(result.Mailboxes), "alerts", len(result.Alerts))
	ok(w, map[string]any{
		"message": "operation:" + itoa(summary.TotalEmails) + " operation," +
			itoa(summary.TotalAlerts) + " operation",
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
