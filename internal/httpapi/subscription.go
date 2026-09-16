package httpapi

import (
	"encoding/json"
	"net/http"
	"time"

	"github.com/itswl/balance-alert/internal/model"
	"github.com/itswl/balance-alert/internal/subscription"
)

// requireSubscriptions 订阅是可选能力，没开时整组接口 503。
func (s *Server) requireSubscriptions(w http.ResponseWriter) bool {
	if s.Settings.EnableSubscriptions {
		return true
	}
	fail(w, http.StatusServiceUnavailable, "订阅功能未启用，请设置 ENABLE_SUBSCRIPTIONS=true")
	return false
}

func (s *Server) handleListSubscriptions(w http.ResponseWriter, r *http.Request) {
	if !s.requireSubscriptions(w) {
		return
	}
	cfg := s.Resolver.Load(r.Context())
	subs := cfg.Subscriptions
	if subs == nil {
		subs = []model.Subscription{}
	}
	etagJSON(w, r, map[string]any{"status": "success", "subscriptions": subs})
}

// subscriptionRequest 里 RenewalDay 用 json.RawMessage 收，
// 因为年付允许写成 "03-15" 字符串，也允许写成 315 数字。
type subscriptionRequest struct {
	Name            string          `json:"name"`
	NewName         *string         `json:"new_name"`
	OwnerProject    *string         `json:"owner_project"`
	CycleType       *string         `json:"cycle_type"`
	RenewalDay      json.RawMessage `json:"renewal_day"`
	AlertDaysBefore *int            `json:"alert_days_before"`
	Amount          *float64        `json:"amount"`
	Enabled         *bool           `json:"enabled"`
	LastRenewedDate *string         `json:"last_renewed_date"`
}

var validCycles = map[string]bool{
	model.CycleWeekly: true, model.CycleMonthly: true, model.CycleYearly: true,
}

func (s *Server) handleAddSubscription(w http.ResponseWriter, r *http.Request) {
	if !s.requireSubscriptions(w) || !s.requireDynamicConfig(w, "订阅配置") {
		return
	}
	var body subscriptionRequest
	if !decodeJSON(w, r, &body) {
		return
	}
	body.Name = trimSpace(body.Name)
	if body.Name == "" {
		failValidation(w, []string{"name: 不能为空"})
		return
	}

	cfg := s.Resolver.Load(r.Context())
	if findSubscription(cfg.Subscriptions, body.Name) != nil {
		fail(w, http.StatusBadRequest, "订阅名称 ["+body.Name+"] 已存在")
		return
	}

	sub := model.Subscription{
		Name: body.Name, CycleType: model.CycleMonthly,
		RenewalDay: 1, AlertDaysBefore: 3, Enabled: true,
	}
	if problems := applySubscriptionPatch(&sub, body); len(problems) > 0 {
		failValidation(w, problems)
		return
	}

	if err := s.Store.UpsertSubscription(r.Context(), sub); err != nil {
		s.log().Error("添加订阅失败", "subscription", body.Name, "error", err)
		fail(w, storeWriteStatus(err), "保存失败")
		return
	}
	s.log().Info("[AUDIT] 添加订阅", "subscription", body.Name, "cycle", sub.CycleType, "amount", sub.Amount)
	s.refreshSubscriptions(r)
	ok(w, map[string]any{"message": "订阅 [" + body.Name + "] 已成功添加"})
}

// handleUpdateSubscription 更新订阅：只改传了的字段；改名时先删旧名再按新名写入。
func (s *Server) handleUpdateSubscription(w http.ResponseWriter, r *http.Request) {
	if !s.requireSubscriptions(w) || !s.requireDynamicConfig(w, "订阅配置") {
		return
	}
	var body subscriptionRequest
	if !decodeJSON(w, r, &body) {
		return
	}

	cfg := s.Resolver.Load(r.Context())
	current := findSubscription(cfg.Subscriptions, body.Name)
	if current == nil {
		fail(w, http.StatusNotFound, "未找到订阅: "+body.Name)
		return
	}

	updated := *current
	if problems := applySubscriptionPatch(&updated, body); len(problems) > 0 {
		failValidation(w, problems)
		return
	}
	if body.NewName != nil && trimSpace(*body.NewName) != "" {
		updated.Name = trimSpace(*body.NewName)
		if err := s.Store.DeleteSubscription(r.Context(), body.Name); err != nil {
			s.log().Warn("改名时删除旧记录失败", "subscription", body.Name, "error", err)
		}
	}

	if err := s.Store.UpsertSubscription(r.Context(), updated); err != nil {
		s.log().Error("更新订阅失败", "subscription", body.Name, "error", err)
		fail(w, storeWriteStatus(err), "保存失败")
		return
	}
	s.log().Info("[AUDIT] 更新订阅", "subscription", body.Name)
	s.refreshSubscriptions(r)
	ok(w, map[string]any{"message": "订阅 [" + body.Name + "] 配置已更新"})
}

// applySubscriptionPatch 把请求里传了的字段盖到订阅上，返回校验问题。
func applySubscriptionPatch(target *model.Subscription, body subscriptionRequest) []string {
	var problems []string

	if body.CycleType != nil {
		if !validCycles[*body.CycleType] {
			problems = append(problems, "cycle_type: 只能是 weekly / monthly / yearly")
		} else {
			target.CycleType = *body.CycleType
		}
	}
	if len(body.RenewalDay) > 0 && string(body.RenewalDay) != "null" {
		day, ok := parseRenewalDay(body.RenewalDay, target.CycleType)
		if !ok {
			problems = append(problems, `renewal_day: 无法识别（年付可写 "03-15"，月付写 1-31，周付写 1-7）`)
		} else {
			target.RenewalDay = day
		}
	}
	if body.AlertDaysBefore != nil {
		if *body.AlertDaysBefore < 0 {
			problems = append(problems, "alert_days_before: 不能为负数")
		} else {
			target.AlertDaysBefore = *body.AlertDaysBefore
		}
	}
	if body.Amount != nil {
		target.Amount = *body.Amount
	}
	if body.Enabled != nil {
		target.Enabled = *body.Enabled
	}
	if body.OwnerProject != nil {
		target.OwnerProject = model.OwnerProjectOf(*body.OwnerProject)
	}
	if body.LastRenewedDate != nil {
		if *body.LastRenewedDate == "" {
			target.LastRenewedDate = nil
		} else if _, err := time.Parse("2006-01-02", *body.LastRenewedDate); err != nil {
			problems = append(problems, "last_renewed_date: 格式应为 YYYY-MM-DD")
		} else {
			target.LastRenewedDate = body.LastRenewedDate
		}
	}
	return problems
}

// parseRenewalDay 同时接受 315 和 "03-15" 两种写法。
func parseRenewalDay(raw json.RawMessage, cycleType string) (int, bool) {
	var asNumber int
	if err := json.Unmarshal(raw, &asNumber); err == nil {
		return asNumber, true
	}
	var asText string
	if err := json.Unmarshal(raw, &asText); err != nil {
		return 0, false
	}
	return subscription.CoerceRenewalDay(asText, cycleType)
}

func (s *Server) handleDeleteSubscription(w http.ResponseWriter, r *http.Request) {
	if !s.requireSubscriptions(w) || !s.requireDynamicConfig(w, "订阅配置") {
		return
	}
	var body nameRequest
	if !decodeJSON(w, r, &body) {
		return
	}
	cfg := s.Resolver.Load(r.Context())
	if findSubscription(cfg.Subscriptions, body.Name) == nil {
		fail(w, http.StatusNotFound, "未找到订阅: "+body.Name)
		return
	}
	if err := s.Store.DeleteSubscription(r.Context(), body.Name); err != nil {
		fail(w, storeWriteStatus(err), "删除失败")
		return
	}
	s.log().Info("[AUDIT] 删除订阅", "subscription", body.Name)
	s.refreshSubscriptions(r)
	ok(w, map[string]any{"message": "订阅 [" + body.Name + "] 已删除"})
}

type renewedRequest struct {
	Name        string  `json:"name"`
	RenewedDate *string `json:"renewed_date"`
}

// handleMarkRenewed 标记订阅本周期已续费，默认今天，返回下次续费日期。
func (s *Server) handleMarkRenewed(w http.ResponseWriter, r *http.Request) {
	if !s.requireSubscriptions(w) || !s.requireDynamicConfig(w, "订阅配置") {
		return
	}
	var body renewedRequest
	if !decodeJSON(w, r, &body) {
		return
	}
	if body.Name == "" {
		fail(w, http.StatusBadRequest, "缺少必要参数: name")
		return
	}

	renewedDate := time.Now().Format("2006-01-02")
	if body.RenewedDate != nil && *body.RenewedDate != "" {
		if _, err := time.Parse("2006-01-02", *body.RenewedDate); err != nil {
			fail(w, http.StatusBadRequest, "renewed_date 格式应为 YYYY-MM-DD")
			return
		}
		renewedDate = *body.RenewedDate
	}

	cfg := s.Resolver.Load(r.Context())
	current := findSubscription(cfg.Subscriptions, body.Name)
	if current == nil {
		fail(w, http.StatusNotFound, "未找到订阅配置")
		return
	}
	updated := *current
	updated.LastRenewedDate = &renewedDate
	if err := s.Store.UpsertSubscription(r.Context(), updated); err != nil {
		fail(w, storeWriteStatus(err), "更新订阅失败")
		return
	}
	s.log().Info("[AUDIT] 标记已续费", "subscription", body.Name, "date", renewedDate)
	s.refreshSubscriptions(r)

	renewedAt, _ := time.ParseInLocation("2006-01-02", renewedDate, time.Local)
	next, err := subscription.NextRenewalFrom(updated.CycleType, updated.RenewalDay, renewedAt)
	if err != nil {
		fail(w, http.StatusBadRequest, err.Error())
		return
	}
	ok(w, map[string]any{
		"message":           "订阅 [" + body.Name + "] 已标记为已续费",
		"next_renewal_date": next.Format("2006-01-02T15:04:05"),
	})
}

func (s *Server) handleClearRenewed(w http.ResponseWriter, r *http.Request) {
	if !s.requireSubscriptions(w) || !s.requireDynamicConfig(w, "订阅配置") {
		return
	}
	var body nameRequest
	if !decodeJSON(w, r, &body) {
		return
	}
	cfg := s.Resolver.Load(r.Context())
	current := findSubscription(cfg.Subscriptions, body.Name)
	if current == nil {
		fail(w, http.StatusNotFound, "未找到订阅配置")
		return
	}
	updated := *current
	updated.LastRenewedDate = nil
	if err := s.Store.UpsertSubscription(r.Context(), updated); err != nil {
		fail(w, storeWriteStatus(err), "更新订阅失败")
		return
	}
	s.log().Info("[AUDIT] 清除续费标记", "subscription", body.Name)
	s.refreshSubscriptions(r)
	ok(w, map[string]any{"message": "订阅 [" + body.Name + "] 的续费标记已清除"})
}

// refreshSubscriptions 配置变化后重算订阅状态，页面上立刻能看到新的倒计时。
func (s *Server) refreshSubscriptions(r *http.Request) {
	cfg := s.Resolver.Load(r.Context())
	results := s.Subs.Check(r.Context(), cfg.EnabledSubscriptions(), !s.Settings.EnableWebAlarm)
	s.State.SetSubscriptions(results)
	if s.OnSubscriptionUpdated != nil {
		s.OnSubscriptionUpdated(results)
	}
}

func findSubscription(subs []model.Subscription, name string) *model.Subscription {
	for i := range subs {
		if subs[i].Name == name {
			return &subs[i]
		}
	}
	return nil
}
