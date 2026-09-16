package httpapi

import (
	"crypto/md5"
	"encoding/hex"
	"net/http"
	"strings"

	"github.com/itswl/balance-alert/internal/store"
)

// 历史查询的参数默认值与范围，与旧版一致。
func (s *Server) handleBalanceHistory(w http.ResponseWriter, r *http.Request) {
	days, err := intParam(r, "days", 7, 1, 365)
	if err != nil {
		fail(w, http.StatusBadRequest, err.Error())
		return
	}
	limit, err := intParam(r, "limit", 100, 1, 1000)
	if err != nil {
		fail(w, http.StatusBadRequest, err.Error())
		return
	}

	rows, err := s.Store.BalanceHistory(r.Context(), store.BalanceQuery{
		ProjectID: r.URL.Query().Get("project_id"),
		Provider:  r.URL.Query().Get("provider"),
		Days:      days, Limit: limit,
	})
	if err != nil {
		s.log().Error("查询余额历史失败", "error", err)
		fail(w, http.StatusInternalServerError, err.Error())
		return
	}
	if rows == nil {
		rows = []store.BalanceRow{}
	}
	ok(w, map[string]any{"count": len(rows), "data": rows})
}

// handleBalanceTrend 取一个账户的余额趋势。
// 前端可能直接传 "provider:name" 原文，这里换算成入库时的项目 ID。
func (s *Server) handleBalanceTrend(w http.ResponseWriter, r *http.Request) {
	days, err := intParam(r, "days", 30, 1, 365)
	if err != nil {
		fail(w, http.StatusBadRequest, err.Error())
		return
	}
	projectID := r.PathValue("projectID")
	if strings.Contains(projectID, ":") {
		sum := md5.Sum([]byte(projectID))
		projectID = hex.EncodeToString(sum[:])
	}

	trend, err := s.Store.BalanceTrend(r.Context(), projectID, days)
	if err != nil {
		s.log().Error("获取余额趋势失败", "error", err)
		fail(w, http.StatusInternalServerError, err.Error())
		return
	}
	if trend == nil {
		fail(w, http.StatusNotFound, "No data found")
		return
	}
	ok(w, map[string]any{"data": trend})
}

func (s *Server) handleAlertHistory(w http.ResponseWriter, r *http.Request) {
	days, err := intParam(r, "days", 7, 1, 365)
	if err != nil {
		fail(w, http.StatusBadRequest, err.Error())
		return
	}
	limit, err := intParam(r, "limit", 50, 1, 1000)
	if err != nil {
		fail(w, http.StatusBadRequest, err.Error())
		return
	}

	rows, err := s.Store.RecentAlerts(r.Context(), store.AlertQuery{
		ProjectID: r.URL.Query().Get("project_id"),
		AlertType: r.URL.Query().Get("alert_type"),
		Days:      days, Limit: limit,
	})
	if err != nil {
		s.log().Error("查询告警历史失败", "error", err)
		fail(w, http.StatusInternalServerError, err.Error())
		return
	}
	if rows == nil {
		rows = []store.AlertRow{}
	}
	ok(w, map[string]any{"count": len(rows), "data": rows})
}

func (s *Server) handleAlertStats(w http.ResponseWriter, r *http.Request) {
	days, err := intParam(r, "days", 30, 1, 365)
	if err != nil {
		fail(w, http.StatusBadRequest, err.Error())
		return
	}
	stats, err := s.Store.AlertStats(r.Context(), days)
	if err != nil {
		s.log().Error("获取告警统计失败", "error", err)
		fail(w, http.StatusInternalServerError, err.Error())
		return
	}
	if stats == nil {
		fail(w, http.StatusInternalServerError, "数据库未启用")
		return
	}
	ok(w, map[string]any{"data": stats})
}

func (s *Server) handleEmailAlertHistory(w http.ResponseWriter, r *http.Request) {
	days, err := intParam(r, "days", 30, 1, 365)
	if err != nil {
		fail(w, http.StatusBadRequest, err.Error())
		return
	}
	limit, err := intParam(r, "limit", 100, 1, 1000)
	if err != nil {
		fail(w, http.StatusBadRequest, err.Error())
		return
	}

	rows, err := s.Store.EmailAlerts(r.Context(), store.EmailAlertQuery{
		Mailbox: r.URL.Query().Get("mailbox"),
		Days:    days, Limit: limit,
	})
	if err != nil {
		s.log().Error("查询邮件告警历史失败", "error", err)
		fail(w, http.StatusInternalServerError, err.Error())
		return
	}
	if rows == nil {
		rows = []store.EmailAlertRow{}
	}
	ok(w, map[string]any{"count": len(rows), "data": rows})
}
